# Frontier Atlas architecture

## IMPLEMENTED NOW

Bounded async HTTP workers use queues, timeouts, exponential backoff, jitter, `429` handling, and `Retry-After`. `413` provider responses reduce the configured chunk size. Source parsers validate records with Pydantic, preserve URLs and timestamps, reject stale records, and use SQLite unique keys for persistent idempotency. Entity mappings record raw/canonical names, method, confidence, and source URL. CSV/JSONL exports and a Google Sheets dry-run transformation are local outputs. Gemini Flash, Groq Llama, and DeepSeek adapters are implemented but execute only when their environment keys exist.

## PRODUCTION SCALE DESIGN

For 500k+ records, source adapters publish to a durable queue with per-source rate limits and backpressure. Stateless async workers consume bounded batches, store raw HTML/API responses in object storage, and write validated canonical records to PostgreSQL with unique URL/content keys. Redis supplies distributed locks, quotas, quarantine state, and coordination. Failed messages return to a retry queue; dead letters preserve failure reasons. This design is not deployed or load tested locally.

Vector storage is a derived projection for semantic retrieval, while a graph database or graph tables model company, product, paper, author, and repository relationships. Neither projection is authoritative. Freshness tracking stores source date, date method, collection time, and rejection reason. Entity resolution is deterministic first, then conservative fuzzy matching with a confidence threshold.

Observability records source, URL, status, latency, retry count, provider, freshness, and extraction result without secrets. `429` responses honor server delay; `413` responses halve LLM chunks; malformed JSON and Pydantic failures isolate a provider and trigger fallback. A crashed worker can retry the same key. This is at-least-once processing with idempotent writes, not a mathematical exactly-once guarantee.

Anti-bot policy: official APIs first, then RSS/Atom and permitted static HTML. No CAPTCHA solving, authentication bypass, challenge evasion, or aggressive scraping. A blocked source is quarantined and escalated to an approved API or licensed provider.
