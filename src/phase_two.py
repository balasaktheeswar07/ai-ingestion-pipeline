import json
import logging
import time
import xml.etree.ElementTree as ET
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urljoin, urlparse

import aiohttp
from bs4 import BeautifulSoup

from crawler.http_client import AsyncHTTPClient
from entity.resolver import EntityResolver
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


def discover_links(html: str, base_url: str, limit: int) -> list[tuple[str, str]]:
    base_host = urlparse(base_url).netloc
    links: list[tuple[str, str]] = []
    for tag in BeautifulSoup(html, "html.parser").find_all("a", href=True):
        link = urljoin(base_url, tag["href"])
        if urlparse(link).netloc == base_host and link not in {l for l, _ in links}:
            links.append((link, ""))
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
        published = (
            item.findtext("pubDate")
            or item.findtext("dc:date")
            or item.findtext("published")
            or item.findtext("updated")
            or ""
        )
        if link:
            entries.append((link.strip(), published.strip()))
        if len(entries) == limit:
            break
    return entries


def parse_json_jobs(payload: dict, limit: int) -> list[tuple[str, str]]:
    """Parse a Greenhouse-style jobs API response into (job_url, published_date) pairs."""
    entries: list[tuple[str, str]] = []
    for job in payload.get("jobs", []) if isinstance(payload, dict) else []:
        url = job.get("absolute_url") or job.get("url") or ""
        published = (
            job.get("first_published")
            or job.get("updated_at")
            or job.get("published_at")
            or job.get("created_at")
            or ""
        )
        if url:
            entries.append((url, str(published)))
            if len(entries) == limit:
                break
    return entries


def _quarantine(source_url: str, reason: str) -> None:
    """Record a blocked/failed source so the pipeline can back off and report honestly."""
    logger.warning("Source quarantined (%s): %s", reason, source_url)


class SourceQuarantine:
    """Tracks per-source failures and applies source-specific backoff."""

    def __init__(self, max_attempts: int = 2, base_delay: float = 5.0) -> None:
        self.failures: dict[str, int] = {}
        self.max_attempts = max_attempts
        self.base_delay = base_delay

    def record_failure(self, source_url: str) -> None:
        self.failures[source_url] = self.failures.get(source_url, 0) + 1

    def is_quarantined(self, source_url: str) -> bool:
        return self.failures.get(source_url, 0) >= self.max_attempts

    def can_fetch(self, source_url: str) -> bool:
        # Apply backoff proportional to consecutive failures before allowing a retry.
        failures = self.failures.get(source_url, 0)
        if failures > 0:
            delay = self.base_delay * min(2 ** (failures - 1), 32)
            logger.info("Backing off source %s for %.0fs after %d failures", source_url, delay, failures)
            time.sleep(delay)
        return not self.is_quarantined(source_url)


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
    quarantine = SourceQuarantine()
    news, jobs = [], []
    try:
        async with aiohttp.ClientSession() as session:
            # Collect News
            for source in config["news"]:
                if len(news) >= limit:
                    break
                landing = await client.fetch(session, source["url"])
                if not landing:
                    _quarantine(source["url"], "fetch_failed")
                    quarantine.record_failure(source["url"])
                    continue
                try:
                    if source.get("kind") == "rss":
                        links = parse_feed(landing, limit)
                    else:
                        links = discover_links(landing, source["url"], limit)
                except ET.ParseError:
                    _quarantine(source["url"], "invalid_xml")
                    quarantine.record_failure(source["url"])
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
                if not quarantine.can_fetch(source["url"]):
                    _quarantine(source["url"], "quarantined")
                    continue
                company_hint = source["name"].replace("Careers", "").replace("Jobs", "").strip()
                kind = source.get("kind", "html")

                if kind == "api":
                    body = await client.fetch(session, source["url"])
                    if not body:
                        _quarantine(source["url"], "fetch_failed")
                        quarantine.record_failure(source["url"])
                        continue
                    try:
                        payload = json.loads(body)
                        links = parse_json_jobs(payload, limit)
                    except json.JSONDecodeError:
                        _quarantine(source["url"], "invalid_json")
                        quarantine.record_failure(source["url"])
                        continue
                else:
                    landing = await client.fetch(session, source["url"])
                    if not landing:
                        _quarantine(source["url"], "fetch_failed")
                        quarantine.record_failure(source["url"])
                        continue
                    try:
                        links = parse_feed(landing, limit) if source.get("kind") == "rss" else discover_links(landing, source["url"], limit)
                    except ET.ParseError:
                        _quarantine(source["url"], "invalid_xml")
                        quarantine.record_failure(source["url"])
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
