import asyncio
import json
import sys
import unittest
from datetime import UTC, datetime
from pathlib import Path

from pydantic import BaseModel

sys.path.insert(0, str(Path(__file__).parents[1] / "src"))

from crawler.http_client import (
    BLOCKED,
    FORBIDDEN,
    NOT_FOUND,
    RATE_LIMITED,
    SERVER_ERROR,
    SUCCESS,
    TIMEOUT,
    AsyncHTTPClient,
)
from exporter import export_jsonl_files, validate_outputs
from extractors.product import extract_product
from extractors.startup import extract_startup
from llm.engine import ExtractionEngine, LLMProvider
from llm.providers import GeminiProvider
from models.schemas import Product, Startup
from phase_two import parse_feed
from validate_outputs import validate_single_record
from venture_collector import load_venture_sources

FIXTURES_DIR = Path(__file__).parent / "fixtures"


class Result(BaseModel):
    values: list[str] = []


class ChunkRecorder(LLMProvider):
    name = "test"

    def __init__(self) -> None:
        self.prompts: list[str] = []

    async def complete(self, prompt: str) -> str:
        self.prompts.append(prompt)
        return '{"values": ["chunk"]}'


class AssignmentGapTests(unittest.IsolatedAsyncioTestCase):
    async def test_every_chunk_is_processed(self) -> None:
        provider = ChunkRecorder()
        result = await ExtractionEngine([provider], max_input_chars=600, retries=1).extract("a" * 1300, Result)
        self.assertEqual(len(provider.prompts), 3)
        self.assertEqual(result.values, ["chunk"])

    def test_source_backed_venture_records(self) -> None:
        startup = extract_startup("<title>Acme</title><p>We have 125 employees.</p>", "https://example.com/acme", "Example", collected_at=datetime.now(UTC))
        product = extract_product("<title>Acme AI</title><p>Enterprise plans are available. Contact sales.</p>", "https://example.com/product", "Example", collected_at=datetime.now(UTC))
        self.assertIsInstance(startup, Startup)
        self.assertEqual(startup.content.data.employee_count, 125)
        self.assertIsInstance(product, Product)
        self.assertEqual(product.content.pricing_model, "ENTERPRISE")
        self.assertIsNone(extract_product("<title>Acme AI</title><p>Learn more.</p>", "https://example.com/product", "Example").content.pricing_model)

    def test_venture_source_loading(self) -> None:
        sources = load_venture_sources()
        self.assertIn("startups", sources)
        self.assertIn("products", sources)
        self.assertGreaterEqual(len(sources["startups"]), 2)
        self.assertGreaterEqual(len(sources["products"]), 2)
        for s in sources["startups"] + sources["products"]:
            self.assertTrue(s["url"].startswith("http"))
            self.assertTrue(len(s["name"]) > 0)

    def test_startup_json_api_extraction(self) -> None:
        json_data = '{"name": "Hugging Face", "employee_count": 200, "url": "https://huggingface.co"}'
        startup = extract_startup(json_data, "https://huggingface.co", "Hugging Face API")
        self.assertIsNotNone(startup)
        self.assertEqual(startup.content.entity_name, "Hugging Face")
        self.assertEqual(startup.content.data.employee_count, 200)

    def test_product_json_api_extraction(self) -> None:
        json_data = '{"id": "meta-llama/Llama-3-70b", "license": "mit", "pricing": "free"}'
        product = extract_product(json_data, "https://huggingface.co/models", "HF Models")
        self.assertIsNotNone(product)
        self.assertEqual(product.content.startup_name, "meta-llama/Llama-3-70b")
        self.assertEqual(product.content.pricing_model, "FREE")

    def test_rss_entries_preserve_feed_dates(self) -> None:
        entries = parse_feed("<rss><channel><item><link>https://example.com/a</link><pubDate>Thu, 28 Aug 2026 08:00:00 GMT</pubDate></item></channel></rss>", 5)
        self.assertEqual(entries[0][1], "Thu, 28 Aug 2026 08:00:00 GMT")

    def test_output_validation_counts_missing_source(self) -> None:
        record = extract_product("<title>Acme</title>", "https://example.com/product", "Example")
        self.assertEqual(validate_outputs({"products": [record]})["missing_source_urls"], 0)

    def test_validate_single_record_detects_invalid_urls(self) -> None:
        invalid_rec = {"source": {"name": "Test", "url": "not-a-url"}, "title": "Test Paper"}
        valid, reason = validate_single_record(invalid_rec, "research_papers.jsonl")
        self.assertFalse(valid)

    def test_validate_single_record_detects_missing_title(self) -> None:
        invalid_rec = {"source": {"name": "Test", "url": "https://example.com"}, "content": {"paper_url": "https://arxiv.org/abs/1234"}}
        valid, reason = validate_single_record(invalid_rec, "research_papers.jsonl")
        self.assertFalse(valid)

    async def test_provider_not_configured_is_explicit(self) -> None:
        with self.assertRaisesRegex(Exception, "not configured"):
            await GeminiProvider(api_key=None).complete("{}")

    def test_http_retry_after_parser(self) -> None:
        client = AsyncHTTPClient()
        self.assertEqual(client._retry_after_seconds("10"), 10.0)
        self.assertEqual(client._retry_after_seconds("invalid"), None)
        self.assertEqual(client._retry_after_seconds(None), None)