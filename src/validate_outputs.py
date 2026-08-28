import json
import sys
from collections import Counter
from pathlib import Path
from urllib.parse import urlparse

OUTPUT_NAMES = {
    "STARTUP": "STARTUPS",
    "PRODUCT": "PRODUCTS",
    "RESEARCH_PAPER": "RESEARCH PAPERS",
    "JOB_POSTING": "JOBS",
    "NEWS_ARTICLE": "NEWS",
    "ENTITY_MAPPING": "ENTITY MAPPINGS",
}

PRIMARY_FILES = (
    "startups.jsonl",
    "products.jsonl",
    "research_papers.jsonl",
    "jobs.jsonl",
    "news.jsonl",
    "entity_mapping.jsonl",
)


def validate_single_record(record: dict, filename: str) -> tuple[bool, str | None]:
    """Validate that a single record contains required fields and valid URLs."""
    if not isinstance(record, dict):
        return False, "Record is not a valid JSON object"

    # Entity mappings have raw_name and timestamp
    if filename.startswith("entity_mapping"):
        raw_name = record.get("raw_name")
        if not raw_name or not str(raw_name).strip():
            return False, "Missing required raw_name"
        confidence = record.get("confidence")
        if confidence is not None and not (0.0 <= float(confidence) <= 1.0):
            return False, f"Invalid confidence value: {confidence}"
        source_url = record.get("source_url")
        if source_url and not urlparse(str(source_url)).scheme:
            return False, f"Invalid source_url: {source_url}"
        return True, None

    # General records must have source with a valid URL
    source = record.get("source", {})
    if not isinstance(source, dict):
        return False, "Missing or invalid source object"
    url = str(source.get("url", ""))
    if not url or not urlparse(url).scheme:
        return False, f"Missing or invalid source URL: {url}"

    # Record-specific checks
    if filename.startswith("research_papers"):
        content = record.get("content", {})
        if not isinstance(content, dict) or not content.get("title"):
            return False, "Missing required paper title"
        paper_url = str(content.get("paper_url", ""))
        if not paper_url or not urlparse(paper_url).scheme:
            return False, f"Missing or invalid paper_url: {paper_url}"

    elif filename.startswith("news"):
        if not record.get("title"):
            return False, "Missing required news title"
        article_url = str(record.get("article_url", ""))
        if not article_url or not urlparse(article_url).scheme:
            return False, f"Missing or invalid article_url: {article_url}"

    elif filename.startswith("jobs"):
        if not record.get("title"):
            return False, "Missing required job title"
        job_url = str(record.get("job_url", ""))
        if not job_url or not urlparse(job_url).scheme:
            return False, f"Missing or invalid job_url: {job_url}"

    elif filename.startswith("startups"):
        content = record.get("content", {})
        if not isinstance(content, dict) or not content.get("entityName"):
            return False, "Missing required entityName"

    elif filename.startswith("products"):
        content = record.get("content", {})
        if not isinstance(content, dict) or not content.get("startupName"):
            return False, "Missing required startupName"

    return True, None


def validate(directory: Path = Path("data/output")) -> dict[str, int]:
    records: list[dict] = []
    file_records: dict[str, list[dict]] = {}
    invalid_count = 0
    missing_source_count = 0
    seen_identities: set[str] = set()
    duplicate_count = 0

    for filename in PRIMARY_FILES:
        path = directory / filename
        file_records[filename] = []
        if not path.exists():
            continue
        with path.open(encoding="utf-8") as handle:
            for line_idx, line in enumerate(handle, start=1):
                if not line.strip():
                    continue
                try:
                    value = json.loads(line)
                except json.JSONDecodeError:
                    invalid_count += 1
                    continue
                if isinstance(value, dict):
                    valid, reason = validate_single_record(value, filename)
                    if not valid:
                        invalid_count += 1
                    
                    if not filename.startswith("entity_mapping"):
                        source_url = str(value.get("source", {}).get("url", ""))
                        if not source_url:
                            missing_source_count += 1

                    # Identity for duplicate tracking
                    content = value.get("content", {})
                    ident = (
                        content.get("paper_url")
                        or value.get("article_url")
                        or value.get("job_url")
                        or value.get("raw_name")
                        or value.get("source", {}).get("url")
                    )
                    if ident:
                        ident_str = f"{filename}:{ident}"
                        if ident_str in seen_identities:
                            duplicate_count += 1
                        else:
                            seen_identities.add(ident_str)

                    records.append(value)
                    file_records[filename].append(value)

    counts = Counter(record.get("recordType", "UNKNOWN") for record in records)

    papers = [r for r in records if r.get("recordType") == "RESEARCH_PAPER"]
    papers_with_stars = sum(1 for p in papers if p.get("content", {}).get("github_stars") is not None)
    papers_without_stars = len(papers) - papers_with_stars

    mappings = [r for r in records if r.get("recordType") == "ENTITY_MAPPING"]

    report: dict[str, int] = {
        "invalid_records": invalid_count,
        "duplicates": duplicate_count,
        "missing_source_urls": missing_source_count,
        "records": len(records),
        "STARTUPS": counts.get("STARTUP", len(file_records.get("startups.jsonl", []))),
        "PRODUCTS": counts.get("PRODUCT", len(file_records.get("products.jsonl", []))),
        "RESEARCH PAPERS": len(papers),
        "RESEARCH PAPERS WITH GITHUB STARS": papers_with_stars,
        "RESEARCH PAPERS WITHOUT GITHUB STARS": papers_without_stars,
        "JOBS": counts.get("JOB_POSTING", len(file_records.get("jobs.jsonl", []))),
        "NEWS": counts.get("NEWS_ARTICLE", len(file_records.get("news.jsonl", []))),
        "ENTITY MAPPINGS": len(mappings) if mappings else len(file_records.get("entity_mapping.jsonl", [])),
    }

    return report


def main() -> None:
    report = validate()
    print("=" * 50)
    print("AI ECOSYSTEM PIPELINE OUTPUT VALIDATION REPORT")
    print("=" * 50)
    for label in (
        "STARTUPS",
        "PRODUCTS",
        "RESEARCH PAPERS",
        "RESEARCH PAPERS WITH GITHUB STARS",
        "RESEARCH PAPERS WITHOUT GITHUB STARS",
        "JOBS",
        "NEWS",
        "ENTITY MAPPINGS",
    ):
        print(f"  {label:<38}: {report.get(label, 0)}")
    print("-" * 50)
    print(f"  {'TOTAL RECORDS':<38}: {report['records']}")
    print(f"  {'INVALID RECORDS':<38}: {report['invalid_records']}")
    print(f"  {'DUPLICATES':<38}: {report['duplicates']}")
    print(f"  {'MISSING SOURCE URLS':<38}: {report['missing_source_urls']}")
    print("=" * 50)

    if report["invalid_records"] > 0 or report["missing_source_urls"] > 0 or report["duplicates"] > 0:
        print("[FAIL] Output integrity validation detected issues.")
        sys.exit(1)
    else:
        print("[PASS] Output datasets validated successfully.")
        sys.exit(0)


if __name__ == "__main__":
    main()