import asyncio
import json
import logging
from datetime import UTC, datetime
from pathlib import Path

import aiohttp

from crawler.http_client import AsyncHTTPClient
from extractors.product import extract_product
from extractors.startup import extract_startup
from models.schemas import Product, Startup

logger = logging.getLogger(__name__)


def load_venture_sources(path: Path = Path("config/venture_sources.json")) -> dict[str, list[dict[str, str]]]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if set(data) != {"startups", "products"}:
        raise ValueError("venture source configuration must contain startups and products")
    return data


async def collect_ventures(*, config_path: Path = Path("config/venture_sources.json"), concurrency: int = 5) -> tuple[list[Startup], list[Product]]:
    config = load_venture_sources(config_path)
    client = AsyncHTTPClient(max_concurrency=concurrency)
    startups: list[Startup] = []
    products: list[Product] = []
    async with aiohttp.ClientSession() as session:
        async def collect_startup(source: dict[str, str]) -> None:
            html = await client.fetch(session, source["url"])
            if html:
                record = extract_startup(html, source["url"], source["name"])
                if record:
                    startups.append(record)

        async def collect_product(source: dict[str, str]) -> None:
            html = await client.fetch(session, source["url"])
            if html:
                record = extract_product(html, source["url"], source["name"])
                if record:
                    products.append(record)

        await asyncio.gather(*(collect_startup(source) for source in config["startups"]))
        await asyncio.gather(*(collect_product(source) for source in config["products"]))
    logger.info("Collected %d startups and %d products", len(startups), len(products))
    return startups, products