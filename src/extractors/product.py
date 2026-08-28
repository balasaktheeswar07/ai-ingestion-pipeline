import json
import re
from datetime import UTC, datetime

from bs4 import BeautifulSoup

from models.schemas import Product, ProductContent, Source


def extract_product(html_or_json: str, url: str, source_name: str, *, startup_name: str | None = None, collected_at: datetime | None = None) -> Product | None:
    """Extract a Product record from HTML markup or JSON string."""
    name: str = startup_name or ""
    pricing_model = None

    # Check if input is structured JSON
    if html_or_json.strip().startswith("{") and html_or_json.strip().endswith("}"):
        try:
            data = json.loads(html_or_json)
            if isinstance(data, dict):
                name = name or data.get("name") or data.get("title") or data.get("product_name") or data.get("id") or ""
                pricing = str(data.get("pricing") or data.get("pricing_model") or data.get("license") or "").lower()
                if "enterprise" in pricing or "custom" in pricing:
                    pricing_model = "ENTERPRISE"
                elif "freemium" in pricing:
                    pricing_model = "FREEMIUM"
                elif "free" in pricing or "open" in pricing or "mit" in pricing or "apache" in pricing:
                    pricing_model = "FREE"
                elif "paid" in pricing or "subscription" in pricing:
                    pricing_model = "PAID"
        except (json.JSONDecodeError, ValueError):
            pass

    if not name:
        soup = BeautifulSoup(html_or_json, "html.parser")
        title = soup.find("meta", attrs={"property": "og:title"}) or soup.find("h1") or soup.find("title")
        raw = title.get("content") if title and title.name == "meta" else title.get_text(" ", strip=True) if title else ""
        name = " ".join(raw.split())

    if not name:
        return None

    if pricing_model is None:
        soup = BeautifulSoup(html_or_json, "html.parser")
        text = soup.get_text(" ", strip=True).lower()
        if re.search(r"\b(?:enterprise|custom pricing|contact sales|talk to sales|request a quote)\b", text):
            pricing_model = "ENTERPRISE"
        elif re.search(r"\b(?:free tier|free plan|freemium)\b", text):
            pricing_model = "FREEMIUM"
        elif re.search(r"\b(?:free open source|free download|100% free|completely free|forever free)\b", text):
            pricing_model = "FREE"
        elif re.search(r"\b(?:paid plan|\$|\/month|pricing plans|plans start at)\b", text):
            pricing_model = "PAID"

    return Product(
        source=Source(name=source_name, url=url),
        content=ProductContent(startupName=name, pricingModel=pricing_model),
        collectedAt=collected_at or datetime.now(UTC),
    )
