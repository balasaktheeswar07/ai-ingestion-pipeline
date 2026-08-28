from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, field_validator


class Source(BaseModel):
    name: str = Field(min_length=1)
    url: HttpUrl


class PaperContent(BaseModel):
    title: str = Field(min_length=1)
    authors: list[str] = Field(default_factory=list)
    paper_url: HttpUrl
    github_url: HttpUrl | None = None
    github_stars: int | None = Field(default=None, ge=0)
    published_date: datetime | None = None

    @field_validator("authors")
    @classmethod
    def unique_nonempty_authors(cls, authors: list[str]) -> list[str]:
        return list(dict.fromkeys(author.strip() for author in authors if author.strip()))


class ResearchPaper(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    schema_version: str = Field(default="1.0", alias="schemaVersion")
    record_type: str = Field(default="RESEARCH_PAPER", alias="recordType")
    source: Source
    content: PaperContent
    collected_at: datetime = Field(alias="collectedAt")


class StartupData(BaseModel):
    employee_count: int | None = Field(default=None, ge=0, alias="employeeCount")


class StartupContent(BaseModel):
    entity_name: str = Field(min_length=1, alias="entityName")
    data: StartupData


class Startup(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    schema_version: str = Field(default="1.0", alias="schemaVersion")
    record_type: str = Field(default="STARTUP", alias="recordType")
    source: Source
    content: StartupContent
    collected_at: datetime = Field(alias="collectedAt")


class ProductContent(BaseModel):
    startup_name: str = Field(min_length=1, alias="startupName")
    pricing_model: Literal["FREE", "FREEMIUM", "PAID", "ENTERPRISE"] | None = Field(default=None, alias="pricingModel")


class Product(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    schema_version: str = Field(default="1.0", alias="schemaVersion")
    record_type: str = Field(default="PRODUCT", alias="recordType")
    source: Source
    content: ProductContent
    collected_at: datetime = Field(alias="collectedAt")


class NewsArticle(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    schema_version: str = Field(default="1.0", alias="schemaVersion")
    record_type: str = Field(default="NEWS_ARTICLE", alias="recordType")
    source: Source
    title: str = Field(min_length=1)
    article_url: HttpUrl
    text: str = Field(min_length=1)
    content_hash: str
    published_at: datetime | None = None
    date_confidence: str = "unknown"
    date_source: str | None = None
    collected_at: datetime = Field(alias="collectedAt")


class JobPosting(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    schema_version: str = Field(default="1.0", alias="schemaVersion")
    record_type: str = Field(default="JOB_POSTING", alias="recordType")
    source: Source
    job_url: HttpUrl
    company: str | None = None
    title: str = Field(min_length=1)
    published_at: datetime | None = None
    remote_eligible: bool | None = None
    role_family: str | None = None
    date_confidence: str = "unknown"
    date_source: str | None = None
    collected_at: datetime = Field(alias="collectedAt")


class EntityMapping(BaseModel):
    raw_name: str
    normalized_name: str
    canonical_name: str | None = None
    match_method: str
    confidence: float = Field(ge=0, le=1)
    source_url: HttpUrl | None = None
    timestamp: datetime
