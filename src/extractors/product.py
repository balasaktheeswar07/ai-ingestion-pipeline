import re
from datetime import UTC, datetime

from bs4 import BeautifulSoup

from models.schemas import Product, ProductContent, Source


def extract_product(html: str, url: str, source_name: str, *, startup_name: str | None = None, collected_at: datetime | None = None) -> Product | None:
	soup = BeautifulSoup(html, "html.parser")
	title = soup.find("meta", attrs={"property": "og:title"}) or soup.find("h1") or soup.find("title")
	name = startup_name or (title.get("content") if title and title.name == "meta" else title.get_text(" ", strip=True) if title else "")
	if not name:
		return None
	text = soup.get_text(" ", strip=True).lower()
	pricing_model = None
	if re.search(r"enterprise|custom pricing|contact sales", text):
		pricing_model = "ENTERPRISE"
	elif re.search(r"free tier|free plan|freemium", text):
		pricing_model = "FREEMIUM"
	elif re.search(r"\bfree\b", text):
		pricing_model = "FREE"
	elif re.search(r"\bpaid\b|\bpricing\b|\bplans start", text):
		pricing_model = "PAID"
	return Product(source=Source(name=source_name, url=url), content=ProductContent(startupName=name, pricingModel=pricing_model), collectedAt=collected_at or datetime.now(UTC))
