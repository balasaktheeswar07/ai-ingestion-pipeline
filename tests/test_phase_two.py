import sys
import unittest
from datetime import UTC, datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1] / "src"))

from extractors.jobs import extract_job
from extractors.news import extract_article
from storage.database import IdempotencyStore
from utils.dates import is_fresh, normalize_date

HTML = "<meta property='og:title' content='AI update'><meta property='article:published_time' content='2026-08-28T08:00:00Z'><article><p>This is legitimate article content with enough words to extract reliably.</p></article>"

class PhaseTwoTests(unittest.TestCase):
    def test_dates_and_freshness(self) -> None:
        now = datetime(2026, 8, 28, 10, tzinfo=UTC)
        self.assertEqual(normalize_date("2 hours ago", now=now)[0], now - timedelta(hours=2))
        self.assertTrue(is_fresh(now - timedelta(hours=23), now=now))
        self.assertFalse(is_fresh(now - timedelta(hours=25), now=now))

    def test_article_and_job_extraction(self) -> None:
        article = extract_article(HTML, "https://example.com/article", "Example", collected_at=datetime(2026, 8, 28, 10, tzinfo=UTC))
        job = extract_job(HTML.replace("AI update", "Remote AI Engineer"), "https://example.com/job", "Example", collected_at=datetime(2026, 8, 28, 10, tzinfo=UTC))
        self.assertEqual(article.title, "AI update")
        self.assertEqual(job.role_family, "engineering")
        self.assertTrue(job.remote_eligible)

    def test_persistent_duplicate_claim(self) -> None:
        path = Path("data/processed/test_idempotency.db")
        store = IdempotencyStore(path)
        self.assertTrue(store.claim("same", "NEWS_ARTICLE"))
        self.assertFalse(store.claim("same", "NEWS_ARTICLE"))
        store.close()
        path.unlink(missing_ok=True)
