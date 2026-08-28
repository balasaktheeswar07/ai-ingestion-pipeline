import argparse
import asyncio
import logging
from pathlib import Path

from crawler.http_client import AsyncHTTPClient
from paper_collector import PaperCollector, write_jsonl
from phase_two import collect_phase_two
from venture_collector import collect_ventures

DEFAULT_URLS = ["https://arxiv.org/abs/1706.03762"]


async def main(urls: list[str], concurrency: int, output: Path) -> int:
    logging.basicConfig(level=logging.INFO, format="[%(levelname)s] %(message)s")
    logging.info("Starting paper collection")
    papers = await PaperCollector(AsyncHTTPClient(concurrency), workers=concurrency).collect(urls)
    write_jsonl(papers, output)
    logging.info("Wrote %d validated records to %s", len(papers), output)
    return len(papers)


async def arxiv_urls(limit: int, client: AsyncHTTPClient) -> list[str]:
    urls: list[str] = []
    async with __import__("aiohttp").ClientSession() as session:
        for start in range(0, limit, min(100, limit)):
            endpoint = f"https://export.arxiv.org/api/query?search_query=cat:cs.AI&start={start}&max_results={min(100, limit - start)}&sortBy=submittedDate&sortOrder=descending"
            body = await client.fetch(session, endpoint, headers={"Accept": "application/atom+xml"})
            if not body:
                break
            try:
                root = __import__("xml.etree.ElementTree", fromlist=["ElementTree"]).fromstring(body)
            except __import__("xml.etree.ElementTree", fromlist=["ElementTree"]).ParseError:
                break
            page = [item.text.strip() for item in root.findall("{http://www.w3.org/2005/Atom}entry/{http://www.w3.org/2005/Atom}id") if item.text]
            urls.extend(url for url in page if "/abs/" in url)
            if len(page) < min(100, limit - start):
                break
    return urls[:limit]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Collect Phase I research-paper records.")
    parser.add_argument("urls", nargs="*", help="ArXiv or Papers with Code paper URLs")
    parser.add_argument("--input", type=Path, help="Text file containing one source URL per line")
    parser.add_argument("--concurrency", type=int, default=10)
    parser.add_argument("--output", type=Path, default=Path("data/output/research_papers.jsonl"))
    parser.add_argument("--phase", choices=("1", "2", "3"), default="1")
    parser.add_argument("--limit", type=int, default=10)
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    if args.phase == "2":
        async def run_phase_two() -> None:
            news, jobs = await collect_phase_two(limit=args.limit)
            write_jsonl(news, Path("data/output/news.jsonl"))
            write_jsonl(jobs, Path("data/output/jobs.jsonl"))
        asyncio.run(run_phase_two())
        raise SystemExit(0)
    if args.phase == "3":
        async def run_phase_three() -> None:
            startups, products = await collect_ventures(concurrency=args.concurrency)
            write_jsonl(startups, Path("data/output/startups.jsonl"))
            write_jsonl(products, Path("data/output/products.jsonl"))
        asyncio.run(run_phase_three())
        raise SystemExit(0)
    if args.concurrency < 1:
        raise SystemExit("--concurrency must be at least 1")
    file_urls = args.input.read_text(encoding="utf-8").splitlines() if args.input else []
    if file_urls or args.urls:
        urls = [url.strip() for url in (file_urls or args.urls) if url.strip()][:args.limit]
        asyncio.run(main(urls, args.concurrency, args.output))
    else:
        async def run_bulk() -> None:
            client = AsyncHTTPClient(args.concurrency)
            urls = await arxiv_urls(args.limit, client)
            count = await PaperCollector(client, workers=args.concurrency).collect_to_jsonl(urls, args.output)
            logging.info("Wrote %d validated records to %s", count, args.output)
        asyncio.run(run_bulk())
    
