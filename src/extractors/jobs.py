from datetime import UTC, datetime

from bs4 import BeautifulSoup

from models.schemas import JobPosting, Source
from utils.dates import date_from_html


def role_family(title: str) -> str | None:
    lowered = title.lower()
    for family, terms in {"engineering": ("engineer", "developer"), "research": ("research", "scientist"), "product": ("product",), "data": ("data", "analytics")}.items():
        if any(term in lowered for term in terms):
            return family
    return None


def extract_job(html: str, url: str, source_name: str, *, company: str | None = None, collected_at: datetime | None = None) -> JobPosting | None:
    soup = BeautifulSoup(html, "html.parser")
    title_tag = soup.find("meta", attrs={"property": "og:title"}) or soup.find("h1") or soup.find("title")
    title = (title_tag.get("content") if title_tag and title_tag.name == "meta" else title_tag.get_text(" ", strip=True) if title_tag else "")
    if not title:
        return None
    date, confidence, date_source = date_from_html(html, now=collected_at)
    visible = f"{title} {soup.get_text(' ', strip=True)}".lower()
    remote = True if "remote" in visible else None
    return JobPosting(source=Source(name=source_name, url=url), job_url=url, company=company, title=title, published_at=date, remote_eligible=remote, role_family=role_family(title), date_confidence=confidence, date_source=date_source, collectedAt=collected_at or datetime.now(UTC))
