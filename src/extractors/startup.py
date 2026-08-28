import re
from datetime import UTC, datetime

from bs4 import BeautifulSoup

from models.schemas import Source, Startup, StartupContent, StartupData


def extract_startup(html: str, url: str, source_name: str, *, collected_at: datetime | None = None) -> Startup | None:
	soup = BeautifulSoup(html, "html.parser")
	title = soup.find("meta", attrs={"property": "og:site_name"}) or soup.find("h1") or soup.find("title")
	entity_name = title.get("content") if title and title.name == "meta" else title.get_text(" ", strip=True) if title else ""
	text = soup.get_text(" ", strip=True)
	match = re.search(r"(?:over|more than|approximately|about)?\s*(\d[\d,]*)\s*(?:employees|team members|people)\b", text, re.I)
	if not entity_name or not match:
		return None
	employee_count = int(match.group(1).replace(",", ""))
	return Startup(source=Source(name=source_name, url=url), content=StartupContent(entityName=entity_name, data=StartupData(employeeCount=employee_count)), collectedAt=collected_at or datetime.now(UTC))
