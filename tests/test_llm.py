import sys
import unittest
from pathlib import Path

from pydantic import BaseModel

sys.path.insert(0, str(Path(__file__).parents[1] / "src"))

from llm.chunking import chunk_text
from llm.engine import ExtractionEngine, LLMProvider, ProviderError

class Result(BaseModel):
    value: str

class Failing(LLMProvider):
    name = "gemini"
    async def complete(self, prompt: str) -> str:
        raise ProviderError("429")

class Working(LLMProvider):
    name = "groq"
    async def complete(self, prompt: str) -> str:
        return '{"value":"source backed"}'

class LLMTests(unittest.IsolatedAsyncioTestCase):
    async def test_fallback_and_validation(self) -> None:
        result = await ExtractionEngine([Failing(), Working()], retries=1).extract("content", Result)
        self.assertEqual(result.value, "source backed")

    async def test_oversized_recovery(self) -> None:
        class TooLargeThenWorks(LLMProvider):
            name = "deepseek"
            async def complete(self, prompt: str) -> str:
                if len(prompt) > 600:
                    raise ProviderError("413", oversized=True)
                return '{"value":"ok"}'
        result = await ExtractionEngine([TooLargeThenWorks()], max_input_chars=1200, retries=1).extract("x" * 1000, Result)
        self.assertEqual(result.value, "ok")

    def test_chunks_are_bounded(self) -> None:
        self.assertTrue(all(len(chunk.text) <= 100 for chunk in chunk_text("x" * 180, max_chars=100)))
