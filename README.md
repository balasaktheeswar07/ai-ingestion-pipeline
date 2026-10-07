# AI Ecosystem Data Ingestion Pipeline

This repository implements a robust, source-traceable AI ecosystem data ingestion and structured intelligence pipeline. It extracts validated records for research papers, fresh ecosystem news, AI job openings, emerging startups, and AI products with persistent SQLite idempotency, deterministic entity resolution, Pydantic schema validation, LLM fallback extraction, and multi-channel export (JSONL, CSV, Google Sheets).
demo video:https://drive.google.com/file/d/1_6HwBNnsMRCA2wSGEC3BEGo7Kn3u-LS1/view?usp=sharing
I really encourage you to drop your comments here, let's make this more innovative
> **Data Integrity Guarantee**: Live record counts depend on source availability and API credentials. The pipeline never fabricates records to satisfy quotas.

---

## Architecture Overview

```text
[ Configured Sources / APIs / Feeds ]
                  │
                  ▼
   [ AsyncHTTPClient (Bounded Concurrency, Backoff, Retry-After) ]
                  │
                  ▼
     [ Source Parsers & Extractors ] ──► [ LLM Engine (Gemini -> Groq -> DeepSeek) ]
                  │
                  ▼
     [ Pydantic Schema Validation ]
                  │
                  ▼
       [ IdempotencyStore (SQLite) ] ──► [ EntityResolver -> entity_mapping.jsonl ]
                  │
                  ▼
 [ Canonical Output (JSONL) ] ──► [ CSV Exporter ] ──► [ Google Sheets Exporter ]
```

### Implemented Locally
- **Asynchronous HTTP Client**: Semaphore-bounded concurrency, exponential backoff with jitter, HTTP `429` `Retry-After` header parsing, timeout recovery, and standardized error classification (`SUCCESS`, `RATE_LIMITED`, `FORBIDDEN`, `NOT_FOUND`, `TIMEOUT`, `SERVER_ERROR`, `BLOCKED`).
- **Research Paper Ingestion**: Dual-source collection across arXiv and Papers with Code with exact GitHub link extraction and star enrichment via GitHub API.
- **Phase II Freshness Tracking**: Ingestion of 5 news feeds and 5 job boards with JSON-LD, meta, `<time>`, and relative date parsing, enforcing strict 24-hour freshness.
- **Venture Directory Collection**: Ingestion of AI startups and products from public JSON APIs and structured HTML directories with explicit pricing and team size extraction.
- **Deterministic Entity Resolution**: Normalization, legal suffix stripping (`Inc`, `LLC`, `Corp`, `PBC`, `Ltd`, `Technologies`), alias indexing, and strict conservative fuzzy matching (`ratio >= 0.92`, min length 4) with persistence to `entity_mapping.jsonl`.
- **LLM Extraction Engine**: Structured schema extraction with provider fallback (`Gemini Flash` → `Groq Llama` → `DeepSeek`), anti-fabrication prompt governance, and dynamic HTTP `413` chunk halving.
- **Persistent Storage & Idempotency**: SQLite database with unique composite fingerprint indexes preventing duplicate ingestion.
- **Export Pipelines**: Conversion of all 6 datasets to clean UTF-8 CSVs and Google Sheets `--dry-run` or `--upload`.
- **Validation Engine**: Independent dataset integrity verification and exit code status reporting.

### Production Scaling Architecture (500k+ Records)
- **Message Bus / Ingestion Queue**: Kafka / RabbitMQ partitioned by source domain with backpressure.
- **Raw Object Storage**: S3 / Google Cloud Storage for archiving raw HTML/JSON responses before parsing.
- **Canonical Database**: PostgreSQL with range-partitioned tables and unique composite constraints on source URLs and content hashes.
- **Distributed State & Rate Limiting**: Redis clusters managing token-bucket quotas, distributed locks, source quarantine status, and deduplication caches.
- **Downstream Projections**: Read-only pgvector/Pinecone vector indexes for semantic discovery and Neo4j graph projections for lineage.

---

## Repository Structure

```text
├── src/
│   ├── main.py                 # Unified CLI entrypoint
│   ├── paper_collector.py      # arXiv & Papers with Code collector
│   ├── phase_two.py            # News & Jobs freshness collector
│   ├── venture_collector.py    # Startup & Product directory collector
│   ├── exporter.py             # CSV export & tab serialization
│   ├── export_all.py           # CLI script to generate all 6 CSVs
│   ├── sheets_exporter.py      # Google Sheets dry-run & live upload
│   ├── validate_outputs.py     # Independent dataset validator CLI
│   ├── crawler/
│   │   ├── http_client.py      # Bounded async HTTP client with retry logic
│   │   └── base.py             # Crawler base interfaces
│   ├── extractors/
│   │   ├── paper.py            # Paper metadata & GitHub star link extractor
│   │   ├── startup.py          # Startup entity & employee count parser
│   │   ├── product.py          # Product name & pricing model parser
│   │   ├── news.py             # Article text & date parser (Trafilatura)
│   │   └── jobs.py             # Career posting & role family parser
│   ├── llm/
│   │   ├── engine.py           # LLM engine with chunking & Pydantic validation
│   │   ├── providers.py        # Gemini, Groq, DeepSeek HTTP adapters
│   │   └── chunking.py         # Semantic text chunking utilities
│   ├── models/
│   │   └── schemas.py          # Pydantic data schemas
│   ├── storage/
│   │   └── database.py         # SQLite idempotency store
│   ├── entity/
│   │   └── resolver.py         # Entity resolver & mapping logger
│   └── utils/
│       └── dates.py            # Multi-format date parsing & freshness filter
├── config/
│   ├── sources.json            # Phase II news & job source configurations
│   ├── venture_sources.json    # Startup & product source configurations
│   └── entities.json           # Canonical entity seeds and aliases
├── data/
│   ├── output/                 # JSONL, CSV, and validation output files
│   └── processed/              # SQLite idempotency databases
├── docs/
│   ├── architecture.md         # Extended architecture document
│   ├── anti_bot_strategy.md    # Ethical scraping and anti-bot policies
│   └── build_architecture_pdf.py # ReportLab architecture PDF generator
├── tests/
│   ├── fixtures/               # Deterministic HTML/JSON test fixtures
│   ├── test_paper_phase_one.py # Paper extraction & GitHub star tests
│   ├── test_phase_two.py       # News, jobs, and date parsing tests
│   ├── test_entity_export.py   # Entity resolution & export tests
│   ├── test_llm.py             # LLM provider fallback & chunking tests
│   ├── test_assignment_gaps.py # Schema & venture parsing tests
│   └── test_crawler_and_scale.py # HTTP client & scale tests
├── architecture.pdf            # 3-page executive architecture summary
├── requirements.txt            # Python dependencies (UTF-8)
├── .env.example                # Environment variable template
└── README.md                   # Project documentation
```

---

## Installation & Setup

### 1. Clone & Setup Virtual Environment
```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

### 2. Configure Environment Variables
Copy `.env.example` to `.env`:
```powershell
cp .env.example .env
```
Populate optional API keys as desired:
- `GEMINI_API_KEY`: Google Gemini API key (for LLM extraction)
- `GROQ_API_KEY`: Groq API key (for Llama fallback)
- `DEEPSEEK_API_KEY`: DeepSeek API key (for fallback)
- `GITHUB_TOKEN`: GitHub personal access token (increases rate limits for star lookups)
- `GOOGLE_SERVICE_ACCOUNT_JSON`: Service account JSON string for Sheets upload
- `GOOGLE_SHEET_ID`: Target Google Spreadsheet ID

*(Note: All unit tests execute 100% offline and do not require external credentials).*

---

## Running the Pipeline

### Phase I: Research Papers (arXiv & Papers with Code)
```powershell
# Ingest up to 1,000 papers across arXiv and Papers with Code with bounded concurrency
python src/main.py --phase 1 --limit 1000 --concurrency 10

# Collect specific sources
python src/main.py --phase papers --source arxiv --limit 20
python src/main.py --phase papers --source paperswithcode --limit 20

# Collect specific URL list from file
python src/main.py --input papers.txt --concurrency 5
```

### Phase II: News & Jobs (24-Hour Freshness Window)
```powershell
python src/main.py --phase 2 --limit 20
```

### Phase III: Venture Ingestion (Startups & Products)
```powershell
python src/main.py --phase 3 --limit 50 --concurrency 5
# Or run individually:
python src/main.py --phase startups --limit 50
python src/main.py --phase products --limit 50
```

---

## Exporting Datasets

### 1. Generate All 6 CSV Files
Converts canonical JSONL files into clean, UTF-8 CSV tables in `data/output/`:
```powershell
python src/export_all.py
```
Generated CSV files:
- `data/output/startups.csv`
- `data/output/products.csv`
- `data/output/research_papers.csv`
- `data/output/jobs.csv`
- `data/output/news.csv`
- `data/output/entity_mapping.csv`

### 2. Google Sheets Export

#### Dry-Run Mode (Local Verification)
Generates `data/output/sheets_dry_run.json` containing the exact payload for the 6 tabs:
```powershell
python src/sheets_exporter.py --dry-run
```

#### Authenticated Live Upload
Requires `GOOGLE_SERVICE_ACCOUNT_JSON` and `GOOGLE_SHEET_ID` in `.env`:
```powershell
python src/sheets_exporter.py --upload
```

---

## Output Validation

Run the standalone validation suite to verify schema compliance, source URL presence, deduplication, and GitHub metrics:
```powershell
python src/validate_outputs.py
```

Validation rules:
- Fails (exit code 1) if any record lacks a valid `source.url` or required primary identifier (`paper_url`, `article_url`, `job_url`, `entityName`).
- Distinguishes missing optional fields (`github_stars = null` is valid) from missing required fields.
- Reports record counts, duplicates, papers with/without stars, and entity resolution distribution.

---

## Running Tests

Run the full deterministic unit test suite (47 tests):
```powershell
python -m unittest discover -s tests -v
```

All 47 tests run hermetically offline using fixtures from `tests/fixtures/` in under 1 second.

---

## Responsible Acquisition & Anti-Bot Strategy

The pipeline complies with ethical data acquisition guidelines:
1. **Public APIs First**: Prefers official endpoints (arXiv API, Papers with Code API, Hugging Face API).
2. **RSS & Microdata**: Uses standard Atom/RSS feeds and structured JSON-LD / OpenGraph markup.
3. **No Anti-Bot Bypass**: Does not use header obfuscation, residential proxy rotation, or CAPTCHA bypass solvers against Cloudflare, Datadome, or login walls.
4. **Honest Status Reporting**: Blocked, forbidden, or rate-limited endpoints are classified (`FORBIDDEN`, `RATE_LIMITED`, `BLOCKED`) and skipped gracefully without inventing fake records.
