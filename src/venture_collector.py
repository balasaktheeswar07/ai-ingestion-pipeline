import asyncio
import json
import logging
from datetime import UTC, datetime
from pathlib import Path

import aiohttp

from crawler.http_client import AsyncHTTPClient
from entity.resolver import EntityResolver
from extractors.product import extract_product
from extractors.startup import extract_startup
from models.schemas import Product, Startup
from storage.database import IdempotencyStore

logger = logging.getLogger(__name__)


def load_venture_sources(path: Path = Path("config/venture_sources.json")) -> dict[str, list[dict[str, str]]]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if set(data) != {"startups", "products"}:
        raise ValueError("venture source configuration must contain startups and products")
    return data


async def collect_ventures(
    *,
    config_path: Path = Path("config/venture_sources.json"),
    concurrency: int = 5,
    limit: int = 100,
    store_path: Path = Path("data/processed/idempotency.db"),
    mapping_log: Path = Path("data/output/entity_mapping.jsonl"),
) -> tuple[list[Startup], list[Product]]:
    config = load_venture_sources(config_path)
    client = AsyncHTTPClient(max_concurrency=concurrency)
    store = IdempotencyStore(store_path)
    resolver = EntityResolver(mapping_log=mapping_log)

    startups: list[Startup] = []
    products: list[Product] = []

    try:
        async with aiohttp.ClientSession() as session:
            async def collect_startup_source(source: dict[str, str]) -> None:
                url = source["url"]
                source_name = source.get("name", "Venture Source")
                kind = source.get("kind", "html")

                if kind == "api":
                    body = await client.fetch(session, url)
                    if not body:
                        return
                    try:
                        data = json.loads(body)
                        items = data if isinstance(data, list) else data.get("results") or data.get("items") or [data]
                        for item in items:
                            if len(startups) >= limit:
                                break
                            if not isinstance(item, dict):
                                continue
                            item_url = item.get("url") or item.get("homepage") or f"{url}#{item.get('name', '')}"
                            record = extract_startup(json.dumps(item), item_url, source_name, collected_at=datetime.now(UTC))
                            if record and store.claim(str(record.source.url), "STARTUP"):
                                resolver.resolve(record.content.entity_name, source_url=str(record.source.url))
                                startups.append(record)
                    except Exception as error:
                        logger.warning("Failed to parse startup API response from %s: %s", url, error)
                else:
                    html = await client.fetch(session, url)
                    if html:
                        record = extract_startup(html, url, source_name, collected_at=datetime.now(UTC))
                        if record and store.claim(str(record.source.url), "STARTUP"):
                            resolver.resolve(record.content.entity_name, source_url=str(record.source.url))
                            startups.append(record)

            async def collect_product_source(source: dict[str, str]) -> None:
                url = source["url"]
                source_name = source.get("name", "Product Source")
                kind = source.get("kind", "html")

                if kind == "api":
                    body = await client.fetch(session, url)
                    if not body:
                        return
                    try:
                        data = json.loads(body)
                        items = data if isinstance(data, list) else data.get("results") or data.get("items") or [data]
                        for item in items:
                            if len(products) >= limit:
                                break
                            if not isinstance(item, dict):
                                continue
                            item_url = item.get("url") or item.get("homepage") or f"{url}#{item.get('id', '')}"
                            record = extract_product(json.dumps(item), item_url, source_name, collected_at=datetime.now(UTC))
                            if record and store.claim(str(record.source.url), "PRODUCT"):
                                resolver.resolve(record.content.startup_name, source_url=str(record.source.url))
                                products.append(record)
                    except Exception as error:
                        logger.warning("Failed to parse product API response from %s: %s", url, error)
                else:
                    html = await client.fetch(session, url)
                    if html:
                        record = extract_product(html, url, source_name, collected_at=datetime.now(UTC))
                        if record and store.claim(str(record.source.url), "PRODUCT"):
                            resolver.resolve(record.content.startup_name, source_url=str(record.source.url))
                            products.append(record)

            await asyncio.gather(*(collect_startup_source(source) for source in config["startups"]))
            await asyncio.gather(*(collect_product_source(source) for source in config["products"]))
    finally:
        store.close()

    logger.info("Collected %d startups and %d products", len(startups), len(products))
    return startups[:limit], products[:limit]