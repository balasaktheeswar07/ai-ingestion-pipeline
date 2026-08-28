import sys
import unittest
from pathlib import Path

from pydantic import BaseModel, Field

sys.path.insert(0, str(Path(__file__).parents[1] / "src"))

from llm.chunking import chunk_text
from llm.engine import ExtractionEngine, LLMProvider, ProviderError
from llm.providers import DeepSeekProvider, GeminiProvider, GroqProvider, HTTPLLMProvider


class Result(BaseModel):
    value: str = ""
    tags: list[str] = Field(default_factory=list)


class Failing(LLMProvider):
    name = "gemini"

    async def complete(self, prompt: str) -> str:
        raise ProviderError("429")


class Working(LLMProvider):
    name = "groq"

    async def complete(self, prompt: str) -> str:
        return '{"value":"source backed", "tags": ["ai", "frontier"]}'


class InvalidJSON(LLMProvider):
    name = "bad_json"

    async def complete(self, prompt: str) -> str:
        return "Not valid JSON at all"


class LLMTests(unittest.IsolatedAsyncioTestCase):
    async def test_fallback_and_validation(self) -> None:
        result = await ExtractionEngine([Failing(), Working()], retries=1).extract("content", Result)
        self.assertIsNotNone(result)
        self.assertEqual(result.value, "source backed")
        self.assertEqual(result.tags, ["ai", "frontier"])

    async def test_invalid_json_triggers_fallback(self) -> None:
        result = await ExtractionEngine([InvalidJSON(), Working()], retries=1).extract("content", Result)
        self.assertIsNotNone(result)
        self.assertEqual(result.value, "source backed")

    async def test_oversized_recovery(self) -> None:
        class TooLargeThenWorks(LLMProvider):
            name = "deepseek"

            async def complete(self, prompt: str) -> str:
                if len(prompt) > 600:
                    raise ProviderError("413", oversized=True)
                return '{"value":"ok"}'

        result = await ExtractionEngine([TooLargeThenWorks()], max_input_chars=1200, retries=1).extract("x" * 1000, Result)
        self.assertIsNotNone(result)
        self.assertEqual(result.value, "ok")

    def test_chunks_are_bounded(self) -> None:
        self.assertTrue(all(len(chunk.text) <= 100 for chunk in chunk_text("x" * 180, max_chars=100)))

    async def test_provider_not_configured_raises_explicitly(self) -> None:
        with self.assertRaisesRegex(ProviderError, "gemini is not configured"):
            await GeminiProvider(api_key=None).complete("test")
        with self.assertRaisesRegex(ProviderError, "groq is not configured"):
            await GroqProvider(api_key=None).complete("test")
        with self.assertRaisesRegex(ProviderError, "deepseek is not configured"):
            await DeepSeekProvider(api_key=None).complete("test")

    def test_retry_delay_calculation(self) -> None:
        self.assertEqual(HTTPLLMProvider._retry_delay("5", 0), 5.0)
        self.assertEqual(HTTPLLMProvider._retry_delay("0", 0), 0.0)
        fallback_delay = HTTPLLMProvider._retry_delay(None, 1)
        self.assertGreaterEqual(fallback_delay, 2.0)
        self.assertLessEqual(fallback_delay, 3.5)
