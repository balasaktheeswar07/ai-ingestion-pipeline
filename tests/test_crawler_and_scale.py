import asyncio
import json
import sys
import unittest
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

sys.path.insert(0, str(Path(__file__).parents[1] / 'src'))

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
from entity.resolver import EntityResolver
from extractors.paper import extract_title, find_github_url
from paper_collector import PaperCollector, paperswithcode_urls
from venture_collector import collect_ventures


class CrawlerAndScaleTests(unittest.IsolatedAsyncioTestCase):
    def test_status_constants(self) -> None:
        self.assertEqual(SUCCESS, 'SUCCESS')
        self.assertEqual(RATE_LIMITED, 'RATE_LIMITED')
        self.assertEqual(FORBIDDEN, 'FORBIDDEN')
        self.assertEqual(NOT_FOUND, 'NOT_FOUND')
        self.assertEqual(TIMEOUT, 'TIMEOUT')
        self.assertEqual(SERVER_ERROR, 'SERVER_ERROR')
        self.assertEqual(BLOCKED, 'BLOCKED')

    def test_http_client_concurrency_initialization(self) -> None:
        client = AsyncHTTPClient(max_concurrency=7, retries=2, timeout=15.0)
        self.assertEqual(client.semaphore._value, 7)
        self.assertEqual(client.retries, 2)
        self.assertEqual(client.timeout, 15.0)

    async def test_paperswithcode_urls_pagination_and_limit(self) -> None:
        mock_payload = {
            'count': 2,
            'next': None,
            'results': [
                {'id': 'paper-1', 'title': 'Paper One', 'url_abs': 'https://arxiv.org/abs/2101.00001'},
                {'id': 'paper-2', 'title': 'Paper Two', 'url_abs': 'https://arxiv.org/abs/2101.00002'},
            ],
        }
        client = AsyncHTTPClient()
        with patch.object(client, 'fetch_json', new_callable=AsyncMock, return_value=mock_payload):
            urls = await paperswithcode_urls(limit=1, client=client)
            self.assertEqual(len(urls), 1)
            self.assertEqual(urls[0], 'https://paperswithcode.com/paper/paper-1')

    async def test_venture_collector_limit_and_entity_log(self) -> None:
        mapping_log = Path("data/output/test_scale_entity_log.jsonl")
        mapping_log.unlink(missing_ok=True)
        db_path = Path("data/processed/test_scale_venture.db")
        db_path.unlink(missing_ok=True)

        sample_startup_html = "<title>Acme AI</title><p>We are a team of 150 employees.</p>"
        sample_product_html = "<title>Acme Cloud</title><p>Enterprise custom pricing available.</p>"
        sample_api_json = '[{"name": "Acme AI", "employee_count": 150, "url": "https://example.com/acme"}]'
        sample_prod_json = '[{"id": "acme/model-1", "pricing": "enterprise", "url": "https://example.com/model"}]'

        async def mock_fetch(self, session, url, **kwargs):
            if "api/organizations" in url:
                return sample_api_json
            if "api/models" in url:
                return sample_prod_json
            if "pricing" in url or "product" in url or "claude" in url or "models" in url:
                return sample_product_html
            return sample_startup_html

        with patch.object(AsyncHTTPClient, "fetch", new=mock_fetch):
            startups, products = await collect_ventures(
                concurrency=2,
                limit=2,
                store_path=db_path,
                mapping_log=mapping_log,
            )
            self.assertLessEqual(len(startups), 2)
            self.assertLessEqual(len(products), 2)
            if startups:
                self.assertEqual(startups[0].content.entity_name, "Acme AI")
            if products:
                self.assertEqual(products[0].content.pricing_model, "ENTERPRISE")

        self.assertTrue(mapping_log.exists())
        mapping_log.unlink(missing_ok=True)
        db_path.unlink(missing_ok=True)


if __name__ == '__main__':
    unittest.main()
