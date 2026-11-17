"""Knowledge-base response models."""

from pydantic import BaseModel, Field


class ArticleSummary(BaseModel):
    slug: str
    title: str
    summary: str


class Article(ArticleSummary):
    body: str


class ArticlePage(BaseModel):
    items: list[ArticleSummary]
    total: int = Field(ge=0)
    limit: int = Field(ge=1, le=100)
    offset: int = Field(ge=0)
