import json
import sys
import unittest
from datetime import UTC, datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1] / "src"))

from extractors.jobs import extract_job, role_family
from extractors.news import extract_article
from phase_two import load_sources, parse_feed
from storage.database import IdempotencyStore
from utils.dates import date_from_html, is_fresh, normalize_date

HTML = "<meta property='og:title' content='AI update'><meta property='article:published_time' content='2026-08-28T08:00:00Z'><article><p>This is legitimate article content with enough words to extract reliably.</p></article>"
FIXTURES_DIR = Path(__file__).parent / "fixtures"


class PhaseTwoTests(unittest.TestCase):
    def test_dates_and_freshness(self) -> None:
        now = datetime(2026, 8, 28, 10, tzinfo=UTC)
        self.assertEqual(normalize_date("2 hours ago", now=now)[0], now - timedelta(hours=2))
        self.assertEqual(normalize_date("30 minutes ago", now=now)[0], now - timedelta(minutes=30))
        self.assertEqual(normalize_date("yesterday", now=now)[0], now - timedelta(days=1))
        self.assertTrue(is_fresh(now - timedelta(hours=23), now=now))
        self.assertFalse(is_fresh(now - timedelta(hours=25), now=now))

    def test_jsonld_and_html_date_extraction(self) -> None:
        news_html = (FIXTURES_DIR / "news_article.html").read_text(encoding="utf-8")
        date, confidence, date_source = date_from_html(news_html)
        self.assertIsNotNone(date)
        self.assertEqual(confidence, "source")
        self.assertTrue(date_source.startswith("meta:") or date_source.startswith("jsonld:"))

    def test_job_and_role_family_extraction(self) -> None:
        job_html = (FIXTURES_DIR / "job_posting.html").read_text(encoding="utf-8")
        job = extract_job(job_html, "https://example.com/job/123", "Example Careers", company="Acme AI")
        self.assertIsNotNone(job)
        self.assertEqual(job.title, "Senior AI Research Scientist (Remote)")
        self.assertEqual(job.company, "Acme AI")
        self.assertEqual(job.role_family, "research")
        self.assertTrue(job.remote_eligible)
        self.assertEqual(role_family("Software Engineer"), "engineering")
        self.assertEqual(role_family("Product Manager"), "product")
        self.assertEqual(role_family("Data Analyst"), "data")

    def test_article_extraction(self) -> None:
        article = extract_article(HTML, "https://example.com/article", "Example", collected_at=datetime(2026, 8, 28, 10, tzinfo=UTC))
        self.assertIsNotNone(article)
        self.assertEqual(article.title, "AI update")
        self.assertTrue(len(article.text) > 10)
        self.assertEqual(article.source.name, "Example")

    def test_rss_feed_parsing(self) -> None:
        rss_xml = """<rss version="2.0"><channel>
        <item><title>AI Breakthrough</title><link>https://example.com/news/1</link><pubDate>Fri, 28 Aug 2026 08:00:00 GMT</pubDate></item>
        <item><title>Second Article</title><link>https://example.com/news/2</link><pubDate>Fri, 28 Aug 2026 09:00:00 GMT</pubDate></item>
        </channel></rss>"""
        entries = parse_feed(rss_xml, limit=5)
        self.assertEqual(len(entries), 2)
        self.assertEqual(entries[0][0], "https://example.com/news/1")
        self.assertEqual(entries[0][1], "Fri, 28 Aug 2026 08:00:00 GMT")

    def test_sources_configuration_minimums(self) -> None:
        sources = load_sources()
        self.assertGreaterEqual(len(sources["news"]), 5)
        self.assertGreaterEqual(len(sources["jobs"]), 5)
        for entry in sources["news"] + sources["jobs"]:
            self.assertIn("name", entry)
            self.assertIn("url", entry)
            self.assertIn("kind", entry)

    def test_persistent_duplicate_claim(self) -> None:
        path = Path("data/processed/test_idempotency.db")
        store = IdempotencyStore(path)
        self.assertTrue(store.claim("https://example.com/article/1", "NEWS_ARTICLE"))
        self.assertFalse(store.claim("https://example.com/article/1", "NEWS_ARTICLE"))
        store.close()
        path.unlink(missing_ok=True)
