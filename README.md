# Frontier Atlas Pipeline

Frontier Atlas collects source-traceable AI ecosystem records. Deterministic extractors, Pydantic validation, persistent SQLite idempotency, and JSONL/CSV outputs are preferred over invented facts.

## Architecture

`configured source -> bounded async HTTP client -> source parser -> Pydantic record -> persistent idempotency -> JSONL/CSV export`

Implemented now: async HTTP with bounded concurrency, exponential backoff and jitter, `Retry-After`, ArXiv metadata extraction, explicit GitHub links and star lookup, RSS/HTML news and job parsing, startup/product parsing, LLM adapters for Gemini/Groq/DeepSeek, chunk aggregation, SQLite idempotency, entity resolution, CSV export, and Sheets dry-run transformation.

Production-scale design: object storage, a durable queue with backpressure, PostgreSQL canonical storage, Redis coordination/rate limits, horizontal workers, and vector/graph projections. These services are documented but are not deployed locally.

## Setup

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

Copy `.env.example` to `.env`. Provider keys are optional for deterministic tests: `GEMINI_API_KEY`, `GROQ_API_KEY`, `DEEPSEEK_API_KEY`, `GITHUB_TOKEN`, `GOOGLE_SERVICE_ACCOUNT_JSON`, and `GOOGLE_SHEETS_ID`.

## Commands

```powershell
python -m unittest discover -s tests -v
python src/main.py --input papers.txt --concurrency 10
python src/main.py --phase 2 --limit 20
python src/main.py --phase 3 --concurrency 5
python src/validate_outputs.py
```

Phase I writes `data/output/research_papers.jsonl`; with no positional URLs, `--limit 1000` paginates the public ArXiv API. Phase II writes `news.jsonl` and `jobs.jsonl`; Phase III writes `startups.jsonl` and `products.jsonl`. `python src/export_all.py` creates the six CSV outputs. `python src/sheets_exporter.py --dry-run` transforms canonical JSONL locally; `--upload` requires credentials and the optional Sheets dependencies.

## Integrity and limitations

Every record retains a source URL and collection timestamp. Missing facts remain null; GitHub repositories are never inferred from titles, and stars are never fabricated. Fresh news/jobs require a source-backed date within 24 hours. Blocked, challenged, or unavailable sources are skipped and logged; CAPTCHA, authentication, paywall, and bot-control bypass is prohibited.

The checked-in sample contains 10 research-paper records and no guaranteed live startup, product, news, or job records. A 1,000-record target is not claimed. Live provider execution requires keys and network access. Sheets live export requires optional `gspread` and `google-auth` dependencies; without credentials, use dry-run mode.

## Verification

The local deterministic verification currently passes 17 tests. Live source counts and output validation must be generated at collection time because freshness and availability change.
