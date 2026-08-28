import json
import os
import argparse
from collections.abc import Iterable
from pathlib import Path

from pydantic import BaseModel
from pydantic import ConfigDict

TAB_NAMES = ("Startups", "Products", "Research Papers", "Jobs", "News", "Entity Mapping Log")


class RowModel(BaseModel):
    model_config = ConfigDict(extra="allow")


def load_jsonl_records(directory: Path = Path("data/output")) -> dict[str, list[RowModel]]:
    result: dict[str, list[RowModel]] = {}
    for key in ("startups", "products", "research_papers", "jobs", "news", "entity_mapping"):
        path = directory / f"{key}.jsonl"
        result[key] = [RowModel.model_validate(json.loads(line)) for line in path.read_text(encoding="utf-8").splitlines() if line] if path.exists() else []
    return result


def transform_records(records_by_tab: dict[str, Iterable[BaseModel]]) -> dict[str, list[dict[str, object]]]:
    names = ("startups", "products", "research_papers", "jobs", "news", "entity_mapping_log")
    return {tab: [record.model_dump(mode="json", by_alias=True) for record in records_by_tab.get(key, [])] for tab, key in zip(TAB_NAMES, names)}


def export_google_sheets(records_by_tab: dict[str, Iterable[BaseModel]], *, spreadsheet_id: str | None = None, dry_run: bool = False, output: Path = Path("data/output/sheets_dry_run.json")) -> str | None:
    transformed = transform_records(records_by_tab)
    if dry_run:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(transformed, indent=2), encoding="utf-8")
        return None
    if not os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON"):
        raise RuntimeError("Provider configuration error: GOOGLE_SERVICE_ACCOUNT_JSON is required for upload")
    try:
        import gspread
        from google.oauth2.service_account import Credentials
    except ImportError as error:
        raise RuntimeError("Install gspread and google-auth for live Sheets export") from error
    credentials = Credentials.from_service_account_info(json.loads(os.environ["GOOGLE_SERVICE_ACCOUNT_JSON"]), scopes=["https://www.googleapis.com/auth/spreadsheets"])
    target_id = spreadsheet_id or os.getenv("GOOGLE_SHEET_ID") or os.getenv("GOOGLE_SHEETS_ID")
    if not target_id:
        raise RuntimeError("Provider configuration error: GOOGLE_SHEET_ID is required for upload")
    sheet = gspread.authorize(credentials).open_by_key(target_id)
    for tab, rows in transformed.items():
        worksheet = sheet.worksheet(tab) if tab in [item.title for item in sheet.worksheets()] else sheet.add_worksheet(tab, rows=1, cols=1)
        worksheet.clear()
        headers = sorted({key for row in rows for key in row})
        worksheet.update([headers] + [[json.dumps(row.get(header)) if isinstance(row.get(header), (dict, list)) else row.get(header) for header in headers] for row in rows])
    return sheet.url


def main() -> None:
    parser = argparse.ArgumentParser(description="Export canonical output data to Google Sheets")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--dry-run", action="store_true")
    mode.add_argument("--upload", action="store_true")
    args = parser.parse_args()
    from exporter import export_jsonl_files

    export_jsonl_files()
    result = export_google_sheets(load_jsonl_records(), dry_run=args.dry_run)
    print("Sheets dry-run written to data/output/sheets_dry_run.json" if args.dry_run else f"Sheets URL: {result}")


if __name__ == "__main__":
    main()