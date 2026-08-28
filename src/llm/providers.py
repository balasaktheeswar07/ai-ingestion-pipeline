import asyncio
import json
import logging
import os
import random
from abc import ABC, abstractmethod
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from typing import Any

import aiohttp

from llm.engine import ProviderError

logger = logging.getLogger(__name__)


class HTTPLLMProvider(ABC):
    name: str

    def __init__(self, api_key: str | None, *, timeout: float = 60.0, retries: int = 3) -> None:
        self.api_key = api_key
        self.timeout = timeout
        self.retries = retries

    @abstractmethod
    def request(self, prompt: str) -> tuple[str, str, dict[str, Any]]:
        raise NotImplementedError

    @abstractmethod
    def response_text(self, payload: dict[str, Any]) -> str:
        raise NotImplementedError

    async def complete(self, prompt: str) -> str:
        if not self.api_key:
            raise ProviderError(f"{self.name} is not configured", retryable=False)
        url, body, headers = self.request(prompt)
        timeout = aiohttp.ClientTimeout(total=self.timeout)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            for attempt in range(self.retries):
                try:
                    async with session.post(url, json=body, headers=headers) as response:
                        if response.status == 413:
                            raise ProviderError("provider payload too large", oversized=True)
                        if response.status == 429 or 500 <= response.status < 600:
                            if attempt + 1 == self.retries:
                                raise ProviderError(f"{self.name} returned HTTP {response.status}")
                            await asyncio.sleep(self._retry_delay(response.headers.get("Retry-After"), attempt))
                            continue
                        if response.status >= 400:
                            raise ProviderError(f"{self.name} returned HTTP {response.status}", retryable=False)
                        try:
                            payload = json.loads(await response.text())
                            return self.response_text(payload)
                        except (json.JSONDecodeError, KeyError, TypeError, IndexError) as error:
                            raise ProviderError(f"{self.name} returned malformed JSON", retryable=False) from error
                except asyncio.TimeoutError as error:
                    if attempt + 1 == self.retries:
                        raise ProviderError(f"{self.name} timed out") from error
                    await asyncio.sleep(self._retry_delay(None, attempt))
                except aiohttp.ClientError as error:
                    if attempt + 1 == self.retries:
                        raise ProviderError(f"{self.name} request failed") from error
                    await asyncio.sleep(self._retry_delay(None, attempt))
        raise ProviderError(f"{self.name} request failed")

    @staticmethod
    def _retry_delay(retry_after: str | None, attempt: int) -> float:
        if retry_after:
            try:
                return max(0.0, float(retry_after))
            except ValueError:
                try:
                    retry_at = parsedate_to_datetime(retry_after)
                    if retry_at.tzinfo is None:
                        retry_at = retry_at.replace(tzinfo=UTC)
                    return max(0.0, (retry_at - datetime.now(UTC)).total_seconds())
                except (TypeError, ValueError, OverflowError):
                    pass
        return (2**attempt) + random.random()


SYSTEM_INSTRUCTION = (
    "Only extract facts present in the supplied source text. "
    "Use null when a field is not supported. "
    "Do not infer, guess, or fabricate URLs, dates, metrics, employee counts, pricing, GitHub repositories, or other facts."
)


class GeminiProvider(HTTPLLMProvider):
    name = "gemini"

    def __init__(self, api_key: str | None = None, *, model: str = "gemini-2.5-flash", **kwargs: Any) -> None:
        super().__init__(api_key or os.getenv("GEMINI_API_KEY"), **kwargs)
        self.model = model

    def request(self, prompt: str) -> tuple[str, str, dict[str, Any]]:
        body = {
            "system_instruction": {"parts": [{"text": SYSTEM_INSTRUCTION}]},
            "contents": [{"parts": [{"text": prompt}]}],
        }
        return (
            f"https://generativelanguage.googleapis.com/v1beta/models/{self.model}:generateContent?key={self.api_key}",
            body,
            {"Content-Type": "application/json"},
        )

    def response_text(self, payload: dict[str, Any]) -> str:
        return payload["candidates"][0]["content"]["parts"][0]["text"]


class OpenAICompatibleProvider(HTTPLLMProvider):
    model: str
    endpoint: str

    def request(self, prompt: str) -> tuple[str, str, dict[str, Any]]:
        body = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": SYSTEM_INSTRUCTION},
                {"role": "user", "content": prompt},
            ],
            "response_format": {"type": "json_object"},
        }
        return (
            self.endpoint,
            body,
            {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"},
        )

    def response_text(self, payload: dict[str, Any]) -> str:
        return payload["choices"][0]["message"]["content"]


class GroqProvider(OpenAICompatibleProvider):
    name = "groq"
    endpoint = "https://api.groq.com/openai/v1/chat/completions"

    def __init__(self, api_key: str | None = None, *, model: str = "llama-3.3-70b-versatile", **kwargs: Any) -> None:
        super().__init__(api_key or os.getenv("GROQ_API_KEY"), **kwargs)
        self.model = model


class DeepSeekProvider(OpenAICompatibleProvider):
    name = "deepseek"
    endpoint = "https://api.deepseek.com/chat/completions"

    def __init__(self, api_key: str | None = None, *, model: str = "deepseek-chat", **kwargs: Any) -> None:
        super().__init__(api_key or os.getenv("DEEPSEEK_API_KEY"), **kwargs)
        self.model = model