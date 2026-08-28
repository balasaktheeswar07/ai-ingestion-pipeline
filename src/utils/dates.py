import re
import json
from datetime import UTC, datetime, timedelta

from bs4 import BeautifulSoup
from dateutil import parser


def normalize_date(value: str | None, *, now: datetime | None = None) -> tuple[datetime | None, str]:
    """Parse only source-provided timestamps; returns UTC datetime and confidence."""
    if not value or not value.strip():
        return None, "missing"
    now = now or datetime.now(UTC)
    text = value.strip()
    relative = re.fullmatch(r"(\d+)\s+(minute|minutes|hour|hours|day|days)\s+ago", text, re.I)
    if relative:
        amount, unit = int(relative.group(1)), relative.group(2).lower()
        return now - timedelta(**{unit.rstrip("s") + "s": amount}), "relative"
    if text.lower() == "yesterday":
        return now - timedelta(days=1), "relative"
    try:
        parsed = parser.parse(text)
    except (TypeError, ValueError, OverflowError):
        return None, "invalid"
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC), "source"


def date_from_html(html: str, *, now: datetime | None = None) -> tuple[datetime | None, str, str | None]:
    soup = BeautifulSoup(html, "html.parser")
    for attribute, name in (("name", "article:published_time"), ("property", "article:published_time"), ("name", "date"), ("name", "pubdate")):
        tag = soup.find("meta", attrs={attribute: name})
        if tag and tag.get("content"):
            date, confidence = normalize_date(tag["content"], now=now)
            if date:
                return date, confidence, f"meta:{name}"
    tag = soup.find("time")
    if tag:
        date, confidence = normalize_date(tag.get("datetime") or tag.get_text(" ", strip=True), now=now)
        if date:
            return date, confidence, "time"
    for script in soup.find_all("script", attrs={"type": "application/ld+json"}):
        try:
            payload = json.loads(script.string or script.get_text())
        except (TypeError, json.JSONDecodeError):
            continue
        candidates = payload if isinstance(payload, list) else [payload]
        for item in candidates:
            if isinstance(item, dict):
                for key in ("datePublished", "datePosted", "uploadDate"):
                    date, confidence = normalize_date(item.get(key), now=now)
                    if date:
                        return date, confidence, f"jsonld:{key}"
    return None, "missing", None


def is_fresh(published_at: datetime | None, *, now: datetime | None = None, hours: int = 24) -> bool:
    if published_at is None:
        return False
    now = now or datetime.now(UTC)
    return now - timedelta(hours=hours) <= published_at <= now + timedelta(minutes=5)
