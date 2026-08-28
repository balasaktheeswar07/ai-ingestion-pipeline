import asyncio
import json
import logging
import random
from abc import ABC, abstractmethod
from typing import Any

from pydantic import BaseModel, ValidationError

from llm.chunking import chunk_text

logger = logging.getLogger(__name__)


class ProviderError(Exception):
    def __init__(self, message: str, *, retryable: bool = True, oversized: bool = False) -> None:
        super().__init__(message)
        self.retryable, self.oversized = retryable, oversized


class LLMProvider(ABC):
    name: str

    @abstractmethod
    async def complete(self, prompt: str) -> str:
        raise NotImplementedError


EXTRACTION_SYSTEM_INSTRUCTION = (
    "Only extract facts present in the supplied source text. "
    "Use null when a field is not supported. "
    "Do not infer, guess, or fabricate URLs, dates, metrics, employee counts, pricing, GitHub repositories, or other facts."
)


class ExtractionEngine:
    def __init__(self, providers: list[LLMProvider], max_input_chars: int = 12000, retries: int = 3) -> None:
        self.providers, self.max_input_chars, self.retries = providers, max_input_chars, retries
        self._last_error_oversized = False

    @classmethod
    def with_default_providers(cls, **kwargs: Any) -> "ExtractionEngine":
        from llm.providers import DeepSeekProvider, GeminiProvider, GroqProvider

        return cls([GeminiProvider(), GroqProvider(), DeepSeekProvider()], **kwargs)

    async def extract(self, text: str, model: type[BaseModel], *, title: str = "", metadata: str = "") -> BaseModel | None:
        size = self.max_input_chars
        while size >= 100:
            try:
                chunks = chunk_text(text, max_chars=size, title=title, metadata=metadata)
            except ValueError:
                break
            values: list[dict[str, Any]] = []
            oversized = False
            for chunk in chunks:
                result = await self._extract_chunk(chunk.text, model)
                if result is None:
                    if self._last_error_oversized:
                        oversized = True
                        break
                    return None
                values.append(result.model_dump())
            if oversized:
                size //= 2
                logger.warning("Reducing LLM chunk size after provider payload rejection")
                continue
            return model.model_validate(self._merge_values(values))
        return None

    async def _extract_chunk(self, payload: str, model: type[BaseModel]) -> BaseModel | None:
        self._last_error_oversized = False
        for provider in self.providers:
            for attempt in range(self.retries):
                try:
                    response = await provider.complete(payload)
                    return model.model_validate(json.loads(response))
                except ProviderError as error:
                    self._last_error_oversized = error.oversized
                    if error.oversized or not error.retryable or attempt + 1 == self.retries:
                        logger.warning("Provider %s failed: %s", provider.name, type(error).__name__)
                        break
                    await asyncio.sleep((2**attempt) + random.random())
                except (json.JSONDecodeError, ValidationError) as error:
                    logger.warning("Provider %s returned invalid structured output: %s", provider.name, type(error).__name__)
                    break
        return None

    @staticmethod
    def _merge_values(values: list[dict[str, Any]]) -> dict[str, Any]:
        merged: dict[str, Any] = {}
        for value in values:
            for key, item in value.items():
                if item in (None, "", [], {}):
                    continue
                if isinstance(item, list):
                    current = merged.setdefault(key, [])
                    for entry in item:
                        if entry not in current:
                            current.append(entry)
                else:
                    merged.setdefault(key, item)
        return merged
