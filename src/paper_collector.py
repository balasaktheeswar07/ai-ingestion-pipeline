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


def write_jsonl(papers: Iterable[ResearchPaper], output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", encoding="utf-8") as handle:
        for paper in papers:
            handle.write(json.dumps(paper.model_dump(mode="json", by_alias=True), ensure_ascii=False) + "\n")
