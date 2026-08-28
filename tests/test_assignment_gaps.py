import sys
import unittest
from datetime import UTC, datetime
from pathlib import Path

from pydantic import BaseModel

sys.path.insert(0, str(Path(__file__).parents[1] / "src"))

from exporter import validate_outputs
from extractors.product import extract_product
from extractors.startup import extract_startup
from llm.engine import ExtractionEngine, LLMProvider
from llm.providers import GeminiProvider
from models.schemas import Product, Startup
from phase_two import parse_feed


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
        self.assertIsNone(extract_product("<title>Acme AI</title><p>Learn more.</p>", "https://example.com/product", "Example" ).content.pricing_model)

    def test_rss_entries_preserve_feed_dates(self) -> None:
        entries = parse_feed("<rss><channel><item><link>https://example.com/a</link><pubDate>Thu, 28 Aug 2026 08:00:00 GMT</pubDate></item></channel></rss>", 5)
        self.assertEqual(entries[0][1], "Thu, 28 Aug 2026 08:00:00 GMT")

    def test_output_validation_counts_missing_source(self) -> None:
        record = extract_product("<title>Acme</title>", "https://example.com/product", "Example")
        self.assertEqual(validate_outputs({"products": [record]})["missing_source_urls"], 0)

    async def test_provider_not_configured_is_explicit(self) -> None:
        with self.assertRaisesRegex(Exception, "not configured"):
            await GeminiProvider(api_key=None).complete("{}");