import re
from datetime import UTC, datetime
from urllib.parse import urlparse

from bs4 import BeautifulSoup

_ARXIV_ID = re.compile(r"(?:arxiv\.org/(?:abs|pdf)/|arxiv:)(\d{4}\.\d{4,5})(?:v\d+)?", re.I)
_GITHUB_REPOSITORY = re.compile(r"^https?://github\.com/[^/?#]+/[^/?#]+/?$", re.I)


def extract_title(html: str) -> str | None:
    soup = BeautifulSoup(html, "html.parser")
    title_tag = (
        soup.select_one("h1.paper-title")
        or soup.select_one("h1.title")
        or soup.find("meta", attrs={"name": "citation_title"})
        or soup.find("meta", attrs={"property": "og:title"})
        or soup.find("title")
    )
    if not title_tag:
        return None
    value = title_tag.get("content") if title_tag.name == "meta" else title_tag.get_text(" ", strip=True)
    value = re.sub(r"^Title:\s*", "", value or "", flags=re.I)
    value = re.sub(r"\s*\|\s*Papers With Code.*$", "", value, flags=re.I)
    return " ".join(value.split()) or None


def extract_authors(html: str) -> list[str]:
    soup = BeautifulSoup(html, "html.parser")
    author_tags = (
        soup.find_all("meta", attrs={"name": "citation_author"})
        or soup.select("div.authors a")
        or soup.select("span.author-span a")
        or soup.select("span.author-span")
    )
    authors: list[str] = []
    for author in author_tags:
        val = author.get("content") if author.name == "meta" else author.get_text(" ", strip=True)
        cleaned = " ".join((val or "").split()).strip(", ")
        if cleaned and cleaned not in authors:
            authors.append(cleaned)
    return authors


def extract_published_date(html: str) -> str | None:
    soup = BeautifulSoup(html, "html.parser")
    date_tag = (
        soup.find("meta", attrs={"name": "citation_date"})
        or soup.find("meta", attrs={"name": "citation_publication_date"})
        or soup.find("meta", attrs={"property": "article:published_time"})
    )
    if date_tag and date_tag.get("content"):
        normalized = normalize_date(date_tag.get("content"))
        if normalized:
            return normalized

    dateline = soup.select_one("div.dateline") or soup.select_one("span.paper-date")
    if dateline:
        match = re.search(r"\[?(\d{1,2}\s+[A-Za-z]+\s+\d{4})\]?", dateline.get_text(" ", strip=True))
        if match:
            normalized = normalize_date(match.group(1))
            if normalized:
                return normalized

    time_tag = soup.find("time")
    if time_tag:
        normalized = normalize_date(time_tag.get("datetime") or time_tag.get_text(" ", strip=True))
        if normalized:
            return normalized
    return None


def normalize_date(value: str | None) -> str | None:
    if not value:
        return None
    for pattern in ("%Y-%m-%d", "%Y/%m/%d", "%d %b %Y", "%d %B %Y", "%B %d, %Y", "%Y-%m-%dT%H:%M:%SZ", "%Y-%m-%dT%H:%M:%S%z"):
        try:
            return datetime.strptime(value.strip(), pattern).replace(tzinfo=UTC).isoformat()
        except ValueError:
            continue
    # Try generic ISO parser if standard patterns fail
    try:
        from dateutil import parser
        parsed = parser.parse(value.strip())
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=UTC)
        return parsed.astimezone(UTC).isoformat()
    except (TypeError, ValueError, OverflowError):
        return None


def canonical_arxiv_url(url: str, html: str = "") -> str:
    match = _ARXIV_ID.search(url) or _ARXIV_ID.search(html)
    return f"https://arxiv.org/abs/{match.group(1)}" if match else url


def find_github_url(html: str) -> str | None:
    """Only accept an explicit root GitHub repository link in source markup."""
    soup = BeautifulSoup(html, "html.parser")
    for link in soup.find_all("a", href=True):
        href = link["href"].strip()
        if href.startswith("//github.com/"):
            href = f"https:{href}"
        if _GITHUB_REPOSITORY.match(href):
            return href.rstrip("/")
    return None


def has_paperswithcode_evidence(html: str) -> bool:
    """Reject a redirect/error page masquerading as a Papers with Code record."""
    soup = BeautifulSoup(html, "html.parser")
    site_name = soup.find("meta", attrs={"property": "og:site_name"})
    return "papers with code" in soup.get_text(" ", strip=True).lower() or (
        site_name is not None and "papers with code" in (site_name.get("content") or "").lower()
    )


def arxiv_id(url: str) -> str | None:
    match = _ARXIV_ID.search(url)
    return match.group(1).lower() if match else None


def github_repository_path(github_url: str) -> str | None:
    parsed = urlparse(github_url)
    parts = [part for part in parsed.path.split("/") if part]
    return "/".join(parts) if parsed.netloc.lower() == "github.com" and len(parts) == 2 else None
