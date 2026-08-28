import json
from collections import Counter
from pathlib import Path
from urllib.parse import urlparse


OUTPUT_NAMES = {"STARTUP": "STARTUPS", "PRODUCT": "PRODUCTS", "RESEARCH_PAPER": "RESEARCH PAPERS", "JOB_POSTING": "JOBS", "NEWS_ARTICLE": "NEWS", "ENTITY_MAPPING": "ENTITY MAPPINGS"}
PRIMARY_FILES = ("startups.jsonl", "products.jsonl", "research_papers.jsonl", "jobs.jsonl", "news.jsonl", "entity_mapping.jsonl", "entity_mapping_log.jsonl")


def validate(directory: Path = Path("data/output")) -> dict[str, int]:
    records: list[dict] = []
    for filename in PRIMARY_FILES:
        path = directory / filename
        if not path.exists():
            continue
        with path.open(encoding="utf-8") as handle:
            for line in handle:
                try:
                    value = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if isinstance(value, dict):
                    records.append(value)
    counts = Counter(record.get("recordType", "UNKNOWN") for record in records)
    source_urls = [str(record.get("source", {}).get("url", "")) for record in records]
    record_urls = []
    for record in records:
        content = record.get("content", {})
        record_urls.append(str(record.get("article_url") or record.get("job_url") or content.get("paper_url") or ""))
    missing_source = sum(not url for url in source_urls)
    invalid = sum(bool(url) and not urlparse(url).scheme for url in source_urls)
    known_record_urls = [url for url in record_urls if url]
    duplicates = len(known_record_urls) - len(set(known_record_urls))
    report = {"invalid_records": invalid, "duplicates": duplicates, "missing_source_urls": missing_source, "records": len(records)}
    report["RESEARCH PAPERS WITH GITHUB STARS"] = sum(bool(record.get("content", {}).get("github_stars") is not None) for record in records if record.get("recordType") == "RESEARCH_PAPER")
    for record_type, label in OUTPUT_NAMES.items():
        report[label] = counts[record_type]
    return report


def main() -> None:
    report = validate()
    for label in ("STARTUPS", "PRODUCTS", "RESEARCH PAPERS", "RESEARCH PAPERS WITH GITHUB STARS", "JOBS", "NEWS", "ENTITY MAPPINGS"):
        print(f"{label}: {report[label]}")
    print(f"INVALID RECORDS: {report['invalid_records']}")
    print(f"DUPLICATES: {report['duplicates']}")
    print(f"MISSING SOURCE URLS: {report['missing_source_urls']}")


if __name__ == "__main__":
    main()