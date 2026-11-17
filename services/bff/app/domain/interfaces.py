"""BFF service boundaries. None means the requested resource does not exist."""

from typing import Protocol
from uuid import UUID

from app.domain.knowledge import Article, ArticlePage
from app.domain.screening import (
    AnswerReceipt,
    ScreeningResult,
    ScreeningSession,
    SubmitAnswerRequest,
)


class ScreeningService(Protocol):
    async def start(self, survey_id: str) -> ScreeningSession | None: ...

    async def submit_answer(
        self, screening_id: UUID, answer: SubmitAnswerRequest,
    ) -> AnswerReceipt | None: ...

    async def get_results(self, screening_id: UUID) -> ScreeningResult | None: ...

    async def get_pdf(self, screening_id: UUID) -> bytes | None: ...


class KnowledgeBaseService(Protocol):
    async def list_articles(self, limit: int, offset: int) -> ArticlePage: ...

    async def get_article(self, slug: str) -> Article | None: ...
