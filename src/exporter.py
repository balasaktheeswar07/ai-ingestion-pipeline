import csv
import json
from collections.abc import Iterable
from pathlib import Path
from urllib.parse import urlparse

from pydantic import BaseModel


def export_csv(records: Iterable[BaseModel], output: Path) -> None:
    rows = [flatten_row(record.model_dump(mode="json", by_alias=True)) for record in records]
    output.parent.mkdir(parents=True, exist_ok=True)
    fields = sorted({key for row in rows for key in row})
    with output.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def flatten_row(row: dict[str, object]) -> dict[str, object]:
    return {key: json.dumps(value, ensure_ascii=False) if isinstance(value, (dict, list)) else value for key, value in row.items()}


def export_jsonl_files(input_directory: Path = Path("data/output"), output_directory: Path = Path("data/output")) -> dict[str, int]:
    names = {"startups": "startups", "products": "products", "research_papers": "research_papers", "jobs": "jobs", "news": "news", "entity_mapping": "entity_mapping"}
    counts: dict[str, int] = {}
    for output_name, record_type in names.items():
        source = input_directory / f"{record_type}.jsonl"
        rows: list[dict[str, object]] = []
        seen: set[str] = set()
        if source.exists():
            for line in source.read_text(encoding="utf-8").splitlines():
                data = json.loads(line)
                identity = json.dumps(data.get("content", {}).get("paper_url") or data.get("article_url") or data.get("job_url") or data.get("raw_name") or data.get("source", {}).get("url"), sort_keys=True)
                if identity in seen:
                    continue
                seen.add(identity)
                rows.append(flatten_row(data))
        output = output_directory / f"{output_name}.csv"
        output.parent.mkdir(parents=True, exist_ok=True)
        fields = sorted({key for row in rows for key in row})
        with output.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=fields or ["recordType"])
            writer.writeheader()
            writer.writerows(rows)
        counts[output_name] = len(rows)
    return counts


def export_required_tabs(records_by_tab: dict[str, Iterable[BaseModel]], directory: Path = Path("data/export")) -> None:
    """Create the six assignment tab files."""
    for tab in ("startups", "products", "research_papers", "jobs", "news", "entity_mapping_log"):
        export_csv(records_by_tab.get(tab, []), directory / f"{tab}.csv")


def validate_outputs(records_by_tab: dict[str, Iterable[BaseModel]]) -> dict[str, int]:
    records = [record for values in records_by_tab.values() for record in values]
    urls: list[str] = []
    invalid = 0
    for record in records:
        data = record.model_dump(mode="json", by_alias=True)
        source = data.get("source", {})
        if not source.get("url") or not urlparse(str(source["url"])).scheme:
            invalid += 1
        for key in ("article_url", "job_url"):
            if key in data:
                urls.append(str(data[key]))
        content = data.get("content", {})
        if isinstance(content, dict) and content.get("paper_url"):
            urls.append(str(content["paper_url"]))
    duplicates = len(urls) - len(set(urls))
    return {"invalid_records": invalid, "duplicates": duplicates, "missing_source_urls": sum(1 for record in records if not record.source.url), "records": len(records)}


def write_validation_report(records_by_tab: dict[str, Iterable[BaseModel]], output: Path = Path("data/output/validation_report.json")) -> dict[str, int]:
    report = validate_outputs(records_by_tab)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2), encoding="utf-8")
    return report
