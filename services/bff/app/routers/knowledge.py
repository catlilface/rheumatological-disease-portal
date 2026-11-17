from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query

from app.domain.interfaces import KnowledgeBaseService
from app.domain.knowledge import Article, ArticlePage
from app.routers.dependencies import get_knowledge_base_service

router = APIRouter(prefix="/knowledge-base/articles", tags=["knowledge-base"])
Service = Annotated[KnowledgeBaseService, Depends(get_knowledge_base_service)]


@router.get("", response_model=ArticlePage)
async def list_articles(
    service: Service,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> ArticlePage:
    """Browse mock article summaries with limit/offset pagination."""
    return await service.list_articles(limit, offset)


@router.get("/{slug}", response_model=Article)
async def get_article(slug: str, service: Service) -> Article:
    """Read one placeholder knowledge-base article."""
    article = await service.get_article(slug)
    if article is None:
        raise HTTPException(status_code=404, detail="Article not found")
    return article
