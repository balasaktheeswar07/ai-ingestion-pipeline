import asyncio
import json
import logging
import os
import xml.etree.ElementTree as ET
from collections.abc import Iterable
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urlparse

import aiohttp
from dotenv import load_dotenv
from pydantic import ValidationError

from crawler.http_client import AsyncHTTPClient
from extractors.paper import arxiv_id, canonical_arxiv_url, extract_authors, extract_published_date, extract_title, find_github_url, github_repository_path, has_paperswithcode_evidence
from models.schemas import PaperContent, ResearchPaper, Source
from storage.database import IdempotencyStore

logger = logging.getLogger(__name__)


def source_name(url: str) -> str | None:
    host = urlparse(url).netloc.lower()
    if host.endswith("arxiv.org"):
        return "arXiv"
    if host.endswith("paperswithcode.com"):
        return "Papers with Code"
    return None


def paper_identity(paper: ResearchPaper) -> str:
    return arxiv_id(str(paper.content.paper_url)) or str(paper.content.paper_url).rstrip("/").lower()


class PaperCollector:
    def __init__(self, client: AsyncHTTPClient, workers: int = 10, store_path: Path = Path("data/processed/frontier_atlas.db")) -> None:
        self.client, self.workers, self.store_path = client, workers, store_path

    async def collect(self, urls: Iterable[str]) -> list[ResearchPaper]:
        return [paper async for paper in self.iter_collect(urls)]

    async def iter_collect(self, urls: Iterable[str]):
        queue: asyncio.Queue[str | None] = asyncio.Queue(maxsize=self.workers * 2)
        output: asyncio.Queue[ResearchPaper | None] = asyncio.Queue(maxsize=self.workers * 2)
        seen: set[str] = set()
        store = IdempotencyStore(self.store_path)
        try:
            async with aiohttp.ClientSession() as session:
                async def worker() -> None:
                    while (url := await queue.get()) is not None:
                        try:
                            paper = await self.collect_one(session, url)
                            if paper and (identity := paper_identity(paper)) not in seen and store.claim(identity, "RESEARCH_PAPER"):
                                seen.add(identity)
                                await output.put(paper)
                            elif paper:
                                logger.info("Skipping duplicate paper: %s", url)
                        except Exception:
                            logger.exception("Paper skipped: %s", url)
                        finally:
                            queue.task_done()
                async def feeder() -> None:
                    for url in urls:
                        await queue.put(url)
                    for _ in tasks:
                        await queue.put(None)

                tasks = [asyncio.create_task(worker()) for _ in range(self.workers)]
                feed_task = asyncio.create_task(feeder())
                finished = 0
                while finished < self.workers:
                    item = await output.get()
                    if item is None:
                        finished += 1
                    else:
                        yield item
                await feed_task
                await asyncio.gather(*tasks)
        finally:
            store.close()

    async def collect_to_jsonl(self, urls: Iterable[str], output: Path) -> int:
        output.parent.mkdir(parents=True, exist_ok=True)
        count = 0
        with output.open("w", encoding="utf-8") as handle:
            async for paper in self.iter_collect(urls):
                handle.write(json.dumps(paper.model_dump(mode="json", by_alias=True), ensure_ascii=False) + "\n")
                count += 1
        return count

    async def collect_one(self, session: aiohttp.ClientSession, url: str) -> ResearchPaper | None:
        name = source_name(url)
        if name is None:
            logger.warning("Paper skipped; unsupported source URL: %s", url)
            return None
        logger.info("Fetching paper: %s", url)
        html = await self.client.fetch(session, url)
        if html is None:
            return None
        if name == "Papers with Code" and not has_paperswithcode_evidence(html):
            logger.warning("Paper skipped; Papers with Code source did not return a matching page: %s", url)
            return None
        title = extract_title(html)
        if not title:
            logger.warning("Paper skipped; no source-backed title: %s", url)
            return None
        github_url = find_github_url(html)
        stars = await self._github_stars(session, github_url) if github_url else None
        try:
            paper = ResearchPaper(source=Source(name=name, url=url), content=PaperContent(title=title, authors=extract_authors(html), paper_url=canonical_arxiv_url(url, html), github_url=github_url, github_stars=stars, published_date=extract_published_date(html)), collectedAt=datetime.now(UTC))
        except ValidationError as error:
            logger.warning("Paper skipped; invalid source data for %s: %s", url, error)
            return None
        logger.info("Extracted paper: %s", paper.content.title)
        return paper

    async def _github_stars(self, session: aiohttp.ClientSession, github_url: str) -> int | None:
        repository = github_repository_path(github_url)
        if not repository:
            return None
        load_dotenv()
        headers = {"Accept": "application/vnd.github+json"}
        if token := os.getenv("GITHUB_TOKEN"):
            headers["Authorization"] = f"Bearer {token}"
        payload = await self.client.fetch_json(session, f"https://api.github.com/repos/{repository}", headers=headers)
        stars = payload.get("stargazers_count") if payload else None
        if isinstance(stars, int) and stars >= 0:
            logger.info("GitHub stars fetched for %s", repository)
            return stars
        logger.warning("GitHub repository unavailable: %s", github_url)
        return None


async def arxiv_urls(limit: int, client: AsyncHTTPClient) -> list[str]:
    urls: list[str] = []
    async with aiohttp.ClientSession() as session:
        for start in range(0, limit, min(100, limit)):
            endpoint = f"https://export.arxiv.org/api/query?search_query=cat:cs.AI&start={start}&max_results={min(100, limit - start)}&sortBy=submittedDate&sortOrder=descending"
            body = await client.fetch(session, endpoint, headers={"Accept": "application/atom+xml"})
            if not body:
                break
            try:
                root = ET.fromstring(body)
            except ET.ParseError:
                break
            page = [item.text.strip() for item in root.findall("{http://www.w3.org/2005/Atom}entry/{http://www.w3.org/2005/Atom}id") if item.text]
            urls.extend(url for url in page if "/abs/" in url)
            if len(page) < min(100, limit - start):
                break
    return urls[:limit]


async def paperswithcode_urls(limit: int, client: AsyncHTTPClient) -> list[str]:
    urls: list[str] = []
    page_size = min(50, limit)
    async with aiohttp.ClientSession() as session:
        for page in range(1, (limit // page_size) + 2):
            endpoint = f"https://paperswithcode.com/api/v1/papers/?page={page}&items_per_page={page_size}"
            payload = await client.fetch_json(session, endpoint)
            if not payload or not isinstance(payload, dict):
                break
            results = payload.get("results", [])
            if not results:
                break
            for item in results:
                paper_id = item.get("id")
                if paper_id:
                    urls.append(f"https://paperswithcode.com/paper/{paper_id}")
                elif item.get("url_abs"):
                    urls.append(item["url_abs"])
            if len(urls) >= limit or not payload.get("next"):
                break
    return urls[:limit]


async def discover_paper_urls(limit: int, client: AsyncHTTPClient, source: str = "all") -> list[str]:
    if source == "arxiv":
        return await arxiv_urls(limit, client)
    elif source == "paperswithcode":
        return await paperswithcode_urls(limit, client)
    else:  # "all"
        arxiv_limit = (limit + 1) // 2
        pwc_limit = limit // 2
        a_urls = await arxiv_urls(arxiv_limit, client)
        p_urls = await paperswithcode_urls(pwc_limit, client)
        combined = []
        for i in range(max(len(a_urls), len(p_urls))):
            if i < len(a_urls):
                combined.append(a_urls[i])
            if i < len(p_urls):
                combined.append(p_urls[i])
        return combined[:limit]


def write_jsonl(papers: Iterable[ResearchPaper], output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", encoding="utf-8") as handle:
        for paper in papers:
            handle.write(json.dumps(paper.model_dump(mode="json", by_alias=True), ensure_ascii=False) + "\n")
