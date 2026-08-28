import hashlib
from datetime import UTC, datetime

import trafilatura
from bs4 import BeautifulSoup

from models.schemas import NewsArticle, Source
from utils.dates import date_from_html


def extract_article(html: str, url: str, source_name: str, *, collected_at: datetime | None = None) -> NewsArticle | None:
    soup = BeautifulSoup(html, "html.parser")
    title_tag = soup.find("meta", attrs={"property": "og:title"}) or soup.find("h1") or soup.find("title")
    title = (title_tag.get("content") if title_tag and title_tag.name == "meta" else title_tag.get_text(" ", strip=True) if title_tag else "")
    text = trafilatura.extract(html, include_comments=False, include_tables=False) or ""
    if not text:
        semantic = soup.find("article") or soup.find("main")
        text = semantic.get_text(" ", strip=True) if semantic else ""
    if not title or not text:
        return None
    published_at, confidence, date_source = date_from_html(html, now=collected_at)
    return NewsArticle(source=Source(name=source_name, url=url), title=title, article_url=url, text=text, content_hash=hashlib.sha256(text.encode()).hexdigest(), published_at=published_at, date_confidence=confidence, date_source=date_source, collectedAt=collected_at or datetime.now(UTC))
