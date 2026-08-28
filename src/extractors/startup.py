import json
import re
from datetime import UTC, datetime

from bs4 import BeautifulSoup

from models.schemas import Source, Startup, StartupContent, StartupData


def extract_startup(html_or_json: str, url: str, source_name: str, *, entity_name: str | None = None, collected_at: datetime | None = None) -> Startup | None:
    """Extract a Startup record from HTML markup or JSON string."""
    name: str = entity_name or ""
    employee_count: int | None = None

    # Check if input is structured JSON
    if html_or_json.strip().startswith("{") and html_or_json.strip().endswith("}"):
        try:
            data = json.loads(html_or_json)
            if isinstance(data, dict):
                name = name or data.get("name") or data.get("company_name") or data.get("title") or ""
                team_size = data.get("team_size") or data.get("employee_count") or data.get("employees")
                if isinstance(team_size, int) and team_size >= 0:
                    employee_count = team_size
                elif isinstance(team_size, str) and team_size.isdigit():
                    employee_count = int(team_size)
        except (json.JSONDecodeError, ValueError):
            pass

    if not name:
        soup = BeautifulSoup(html_or_json, "html.parser")
        # Prefer a clean site name over a title that may carry a tagline.
        site = soup.find("meta", attrs={"property": "og:site_name"}) or soup.find("meta", attrs={"name": "og:site_name"})
        title = soup.find("meta", attrs={"property": "og:title"}) or soup.find("h1") or soup.find("title")
        if site and site.get("content"):
            name = " ".join(site["content"].split())
        else:
            raw_title = title.get("content") if title and title.name == "meta" else title.get_text(" ", strip=True) if title else ""
            raw_title = re.sub(r"\s*[|·—-]\s*(?:About|Home|Welcome to).*$", "", raw_title, flags=re.I)
            name = " ".join(re.sub(r"^(About|Welcome to|Home)\s*[-|:]\s*", "", raw_title, flags=re.I).split())

    if not name:
        return None

    if employee_count is None:
        soup = BeautifulSoup(html_or_json, "html.parser")
        text = soup.get_text(" ", strip=True)
        match = re.search(r"(?:over|more than|approximately|about)?\s*(\d[\d,]*)\s*(?:employees|team members|people)\b", text, re.I)
        if match:
            try:
                employee_count = int(match.group(1).replace(",", ""))
            except ValueError:
                employee_count = None

    return Startup(
        source=Source(name=source_name, url=url),
        content=StartupContent(entityName=name, data=StartupData(employeeCount=employee_count)),
        collectedAt=collected_at or datetime.now(UTC),
    )
