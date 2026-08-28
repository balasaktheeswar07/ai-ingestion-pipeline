import json
import logging
import xml.etree.ElementTree as ET
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urljoin, urlparse

import aiohttp
from bs4 import BeautifulSoup

from crawler.http_client import AsyncHTTPClient
from extractors.jobs import extract_job
from extractors.news import extract_article
from storage.database import IdempotencyStore
from utils.dates import is_fresh

logger = logging.getLogger(__name__)


def load_sources(path: Path = Path("config/sources.json")) -> dict[str, list[dict[str, str]]]:
    sources = json.loads(path.read_text(encoding="utf-8"))
    if set(sources) != {"news", "jobs"} or any(len(sources[key]) < 5 for key in sources):
        raise ValueError("source configuration must contain at least five news and five job sources")
    return sources


def discover_links(html: str, base_url: str, limit: int) -> list[str]:
    base_host = urlparse(base_url).netloc
    links: list[str] = []
    for tag in BeautifulSoup(html, "html.parser").find_all("a", href=True):
        link = urljoin(base_url, tag["href"])
        if urlparse(link).netloc == base_host and link not in links:
            links.append(link)
            if len(links) == limit:
                break
    return links


def parse_feed(xml: str, limit: int) -> list[tuple[str, str]]:
    root = ET.fromstring(xml)
    entries: list[tuple[str, str]] = []
    for item in root.findall(".//item") + root.findall(".//{http://www.w3.org/2005/Atom}entry"):
        link = item.findtext("link") or ""
        if not link:
            link_tag = item.find("{http://www.w3.org/2005/Atom}link")
            link = link_tag.get("href", "") if link_tag is not None else ""
        published = item.findtext("pubDate") or item.findtext("published") or item.findtext("updated") or ""
        if link:
            entries.append((link.strip(), published.strip()))
        if len(entries) == limit:
            break
    return entries


async def collect_phase_two(
    *,
    limit: int = 20,
    config_path: Path = Path("config/sources.json"),
    store_path: Path = Path("data/processed/idempotency.db"),
    mapping_log: Path = Path("data/output/entity_mapping.jsonl"),
) -> tuple[list, list]:
    config = load_sources(config_path)
    client = AsyncHTTPClient(max_concurrency=5)
    store = IdempotencyStore(store_path)
    resolver = EntityResolver(mapping_log=mapping_log)
    news, jobs = [], []
    try:
        async with aiohttp.ClientSession() as session:
            # Collect News
            for source in config["news"]:
                if len(news) >= limit:
                    break
                landing = await client.fetch(session, source["url"])
                if not landing:
                    continue
                try:
                    links = [(url, published) for url, published in parse_feed(landing, limit)] if source.get("kind") == "rss" else [(url, "") for url in discover_links(landing, source["url"], limit)]
                except ET.ParseError:
                    logger.warning("Source returned invalid RSS/XML: %s", source["url"])
                    continue
                for url, feed_date in links:
                    if len(news) >= limit:
                        break
                    page = await client.fetch(session, url)
                    if not page:
                        continue
                    if feed_date and "published_time" not in page and "datePublished" not in page:
                        page = f'<meta property="article:published_time" content="{feed_date}">{page}'
                    record = extract_article(page, url, source["name"], collected_at=datetime.now(UTC))
                    if record and is_fresh(record.published_at) and store.claim(str(record.article_url), "NEWS_ARTICLE"):
                        news.append(record)

            # Collect Jobs
            for source in config["jobs"]:
                if len(jobs) >= limit:
                    break
                company_hint = source["name"].replace("Careers", "").replace("Jobs", "").strip()
                landing = await client.fetch(session, source["url"])
                if not landing:
                    continue
                try:
                    links = [(url, published) for url, published in parse_feed(landing, limit)] if source.get("kind") == "rss" else [(url, "") for url in discover_links(landing, source["url"], limit)]
                except ET.ParseError:
                    logger.warning("Source returned invalid RSS/XML: %s", source["url"])
                    continue
                for url, feed_date in links:
                    if len(jobs) >= limit:
                        break
                    page = await client.fetch(session, url)
                    if not page:
                        continue
                    if feed_date and "published_time" not in page and "datePublished" not in page:
                        page = f'<meta property="article:published_time" content="{feed_date}">{page}'
                    record = extract_job(page, url, source["name"], company=company_hint, collected_at=datetime.now(UTC))
                    if record and is_fresh(record.published_at) and store.claim(str(record.job_url), "JOB_POSTING"):
                        if record.company:
                            resolver.resolve(record.company, source_url=str(record.job_url))
                        jobs.append(record)
    finally:
        store.close()
    logger.info("Phase II collected %d news and %d jobs", len(news), len(jobs))
    return news[:limit], jobs[:limit]
