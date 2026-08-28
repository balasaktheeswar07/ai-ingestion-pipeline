import argparse
import asyncio
import logging
from pathlib import Path

from crawler.http_client import AsyncHTTPClient
from paper_collector import PaperCollector, discover_paper_urls, write_jsonl
from phase_two import collect_phase_two
from venture_collector import collect_ventures


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="AI Ecosystem Data Pipeline CLI: Collect research papers, news, jobs, startups, and products."
    )
    parser.add_argument(
        "urls",
        nargs="*",
        help="Optional specific paper URLs (arXiv or Papers with Code) to collect directly",
    )
    parser.add_argument(
        "--phase",
        choices=("1", "2", "3", "papers", "news_jobs", "ventures", "startups", "products"),
        default="1",
        help="Pipeline phase to execute (1/papers, 2/news_jobs, 3/ventures, startups, products)",
    )
    parser.add_argument(
        "--source",
        choices=("all", "arxiv", "paperswithcode"),
        default="all",
        help="Source provider for research paper collection (default: all)",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=10,
        help="Maximum number of records to collect (default: 10)",
    )
    parser.add_argument(
        "--concurrency",
        type=int,
        default=10,
        help="Number of concurrent network workers (default: 10)",
    )
    parser.add_argument(
        "--input",
        type=Path,
        help="Text file containing one source URL per line for batch collection",
    )
    parser.add_argument(
        "--output",
        type=Path,
        help="Custom output file path for collected records (defaults to data/output/<type>.jsonl)",
    )
    return parser.parse_args()


async def main() -> int:
    args = parse_args()
    logging.basicConfig(level=logging.INFO, format="[%(levelname)s] %(message)s")

    if args.concurrency < 1:
        logging.error("--concurrency must be at least 1")
        return 1
    if args.limit < 1:
        logging.error("--limit must be at least 1")
        return 1

    # Phase 2: News and Jobs
    if args.phase in ("2", "news_jobs"):
        logging.info("Starting Phase II collection (News & Jobs, limit=%d)...", args.limit)
        news, jobs = await collect_phase_two(limit=args.limit)
        news_out = args.output if args.output else Path("data/output/news.jsonl")
        jobs_out = Path("data/output/jobs.jsonl")
        write_jsonl(news, news_out)
        write_jsonl(jobs, jobs_out)
        logging.info("Wrote %d news articles to %s", len(news), news_out)
        logging.info("Wrote %d job postings to %s", len(jobs), jobs_out)
        return 0

    # Phase 3 / Ventures / Startups / Products
    if args.phase in ("3", "ventures", "startups", "products"):
        logging.info("Starting venture collection (phase=%s, limit=%d)...", args.phase, args.limit)
        startups, products = await collect_ventures(concurrency=args.concurrency, limit=args.limit)
        if args.phase in ("3", "ventures", "startups"):
            s_out = args.output if (args.output and args.phase == "startups") else Path("data/output/startups.jsonl")
            write_jsonl(startups, s_out)
            logging.info("Wrote %d startups to %s", len(startups), s_out)
        if args.phase in ("3", "ventures", "products"):
            p_out = args.output if (args.output and args.phase == "products") else Path("data/output/products.jsonl")
            write_jsonl(products, p_out)
            logging.info("Wrote %d products to %s", len(products), p_out)
        return 0

    # Phase 1: Research Papers (default)
    paper_output = args.output or Path("data/output/research_papers.jsonl")
    client = AsyncHTTPClient(args.concurrency)
    collector = PaperCollector(client, workers=args.concurrency)

    file_urls = args.input.read_text(encoding="utf-8").splitlines() if args.input else []
    if file_urls or args.urls:
        urls = [url.strip() for url in (file_urls or args.urls) if url.strip()][:args.limit]
        logging.info("Collecting %d specified paper URLs...", len(urls))
        count = await collector.collect_to_jsonl(urls, paper_output)
    else:
        logging.info("Discovering up to %d paper URLs (source=%s)...", args.limit, args.source)
        urls = await discover_paper_urls(args.limit, client, source=args.source)
        if not urls:
            logging.warning("No paper URLs discovered. Ensure network access is available.")
            return 0
        count = await collector.collect_to_jsonl(urls, paper_output)

    logging.info("Wrote %d validated research papers to %s", count, paper_output)
    return 0


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    raise SystemExit(exit_code)
