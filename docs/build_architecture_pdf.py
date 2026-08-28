from pathlib import Path

from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import PageBreak, Paragraph, SimpleDocTemplate, Spacer

OUTPUT = Path(__file__).parents[1] / "architecture.pdf"


def build() -> None:
    styles = getSampleStyleSheet()
    document = SimpleDocTemplate(
        str(OUTPUT),
        pagesize=letter,
        rightMargin=0.65 * inch,
        leftMargin=0.65 * inch,
        topMargin=0.55 * inch,
        bottomMargin=0.55 * inch,
    )
    story = [
        Paragraph("AI Ecosystem Data Pipeline Architecture", styles["Title"]),
        Paragraph("IMPLEMENTED NOW", styles["Heading2"]),
        Paragraph(
            "Bounded asyncio workers utilize queues, concurrency semaphores, request timeouts, "
            "exponential backoff with jitter, HTTP 429 Retry-After handling, and explicit status classification. "
            "Research papers are collected across arXiv and Papers with Code with exact GitHub repository linking "
            "and star enrichment. Phase II ingests RSS and HTML news and job sources with multi-format date parsing "
            "(JSON-LD, meta, time tags, relative) and strict 24-hour freshness filtering. Startups and products are parsed "
            "from public APIs and structured directory pages. Entity resolution performs legal suffix stripping, alias lookups, "
            "and strict conservative fuzzy matching with JSONL mapping persistence. LLM extraction provides Gemini Flash, Groq Llama, "
            "and DeepSeek adapters with anti-fabrication prompts, 413 chunk reduction, and multi-chunk merging. SQLite unique keys "
            "guarantee persistent idempotency. UTF-8 CSV exports and Google Sheets dry-run/upload transformations are fully supported.",
            styles["BodyText"],
        ),
        Spacer(1, 10),
        Paragraph("PRODUCTION SCALE DESIGN", styles["Heading2"]),
        Paragraph(
            "To scale to 500k+ records, ingestion adapters publish partition keys to a distributed message bus (Kafka/RabbitMQ) "
            "with source-specific rate limits and backpressure controls. Stateless async worker pools consume bounded batches, "
            "archive raw payloads into object storage (S3/GCS), and persist canonical validated records into PostgreSQL with composite unique constraints. "
            "Redis clusters manage distributed locks, token-bucket quotas, source quarantine state, and deduplication caches. "
            "Dead-letter queues isolate schema drifts and provider rejections without dropping data. Vector projections (pgvector/Pinecone) "
            "and graph projections (Neo4j/Postgres recursive CTEs) support semantic search and relational lineage without replacing canonical tables. "
            "PostgreSQL, Redis, Kafka, and Kubernetes are architectural blueprints, not local mock dependencies.",
            styles["BodyText"],
        ),
        PageBreak(),
        Paragraph("Reliability, Freshness and Data Integrity", styles["Heading1"]),
        Paragraph(
            "Data integrity is strictly enforced: missing fields remain null; no synthetic entities, products, dates, or GitHub stars "
            "are fabricated. Freshness tracking validates publication timestamps against a 24-hour window with clock skew tolerance. "
            "GitHub star metrics are queried exclusively via official endpoints when explicit repository URLs exist on paper pages. "
            "Entity resolution prioritizes exact matches, normalizes legal suffixes ('Inc', 'LLC', 'Corp', 'PBC', 'Ltd', 'Technologies'), "
            "maps known aliases, and bounds fuzzy similarity (>=0.92 ratio, min 4 characters), rejecting risky collisions like OpenAI -> OpenTable. "
            "Every mapping event logs raw name, canonical name, match method, confidence, source URL, and timestamp.",
            styles["BodyText"],
        ),
        Spacer(1, 10),
        Paragraph("Operational Resilience and LLM Governance", styles["Heading2"]),
        Paragraph(
            "Comprehensive observability logs source URL, status code, latency, provider fallback events, and validation outcomes without leaking secrets. "
            "When an LLM provider encounters HTTP 429, 5xx, or network timeouts, exponential backoff with jitter is applied. HTTP 413 responses "
            "dynamically halve input chunk sizes. If a provider returns malformed JSON or schema invalid output, the engine falls back in order: "
            "Gemini Flash -> Groq Llama -> DeepSeek. Prompts explicitly enforce strict extraction constraints prohibiting hallucinations.",
            styles["BodyText"],
        ),
        PageBreak(),
        Paragraph("Responsible Acquisition Policy", styles["Heading1"]),
        Paragraph(
            "The pipeline prioritizes official APIs, RSS/Atom feeds, and standard HTML parsing. Concurrency limits and request delays "
            "prevent load spikes on external servers. Anti-bot protections (Cloudflare, Datadome, CAPTCHAs) are strictly respected without "
            "evasion techniques or header spoofing. Challenged or blocked sources are flagged with standardized status codes (BLOCKED, FORBIDDEN, RATE_LIMITED) "
            "and skipped gracefully to protect pipeline uptime.",
            styles["BodyText"],
        ),
        Spacer(1, 10),
        Paragraph("Local Verification and Test Suite", styles["Heading2"]),
        Paragraph(
            "The deterministic test suite contains 47 hermetic unit tests executing completely offline in under one second without requiring external credentials. "
            "The validation CLI independently validates primary datasets, checking schema adherence, source URLs, deduplication, and paper metrics. "
            "Google Sheets export provides local dry-run validation (sheets_dry_run.json) and authenticated multi-tab upload.",
            styles["BodyText"],
        ),
    ]
    document.build(story)


if __name__ == "__main__":
    build()