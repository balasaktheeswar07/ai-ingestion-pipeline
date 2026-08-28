import asyncio
import json
import logging
import random
from datetime import UTC, datetime
from typing import Any

import aiohttp

logger = logging.getLogger(__name__)

SUCCESS = "SUCCESS"
RATE_LIMITED = "RATE_LIMITED"
FORBIDDEN = "FORBIDDEN"
NOT_FOUND = "NOT_FOUND"
TIMEOUT = "TIMEOUT"
SERVER_ERROR = "SERVER_ERROR"
BLOCKED = "BLOCKED"


class AsyncHTTPClient:
    """One bounded, retrying HTTP client shared by every Phase I source."""

    def __init__(self, max_concurrency: int = 10, retries: int = 3, timeout: float = 30.0) -> None:
        self.semaphore = asyncio.Semaphore(max_concurrency)
        self.retries = retries
        self.timeout = timeout

    async def fetch(self, session: aiohttp.ClientSession, url: str, *, headers: dict[str, str] | None = None) -> str | None:
        body, _ = await self.fetch_with_status(session, url, headers=headers)
        return body

    async def fetch_with_status(self, session: aiohttp.ClientSession, url: str, *, headers: dict[str, str] | None = None) -> tuple[str | None, str]:
        request_headers = {"User-Agent": "FrontierAtlasPhaseI/1.0", "Accept": "text/html,application/json;q=0.9,*/*;q=0.8"}
        if headers:
            request_headers.update(headers)
        async with self.semaphore:
            for attempt in range(self.retries):
                try:
                    async with session.get(
                        url,
                        timeout=aiohttp.ClientTimeout(total=self.timeout),
                        headers=request_headers,
                    ) as response:
                        if response.status == 200:
                            return await response.text(), SUCCESS
                        if response.status == 429:
                            await self._backoff(url, response.status, attempt, response.headers.get("Retry-After"))
                            if attempt + 1 == self.retries:
                                return None, RATE_LIMITED
                            continue
                        if 500 <= response.status < 600:
                            await self._backoff(url, response.status, attempt, response.headers.get("Retry-After"))
                            if attempt + 1 == self.retries:
                                return None, SERVER_ERROR
                            continue
                        if response.status == 403:
                            logger.warning("Source forbidden or blocked (%s): %s", response.status, url)
                            return None, FORBIDDEN
                        if response.status == 404:
                            logger.warning("Source not found: %s", url)
                            return None, NOT_FOUND
                        logger.warning("Request failed (%s): %s", response.status, url)
                        return None, BLOCKED
                except (asyncio.TimeoutError, aiohttp.ClientError) as error:
                    if attempt + 1 == self.retries:
                        logger.error("Request failed after retries: %s (%s)", url, error)
                        return None, TIMEOUT if isinstance(error, asyncio.TimeoutError) else BLOCKED
                    await self._backoff(url, type(error).__name__, attempt, None)
        return None, BLOCKED

    async def fetch_json(self, session: aiohttp.ClientSession, url: str, *, headers: dict[str, str] | None = None) -> dict[str, Any] | None:
        body = await self.fetch(session, url, headers=headers)
        if body is None:
            return None
        try:
            payload = json.loads(body)
        except json.JSONDecodeError:
            logger.warning("Invalid JSON response: %s", url)
            return None
        return payload if isinstance(payload, dict) else None

    async def _backoff(self, url: str, reason: object, attempt: int, retry_after: str | None) -> None:
        wait_time = self._retry_after_seconds(retry_after)
        if wait_time is None:
            wait_time = (2**attempt) + random.random()
        logger.warning("Retrying %s after %s in %.2fs", url, reason, wait_time)
        await asyncio.sleep(wait_time)

    @staticmethod
    def _retry_after_seconds(value: str | None) -> float | None:
        if not value:
            return None
        try:
            return max(0.0, float(value))
        except ValueError:
            try:
                retry_at = datetime.strptime(value, "%a, %d %b %Y %H:%M:%S GMT").replace(tzinfo=UTC)
            except ValueError:
                return None
            return max(0.0, (retry_at - datetime.now(UTC)).total_seconds())
