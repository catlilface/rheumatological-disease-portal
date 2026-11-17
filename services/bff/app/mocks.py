"""Stateless fixtures only: no saved answers, scoring, or PDF generation."""

from importlib.resources import files
from uuid import UUID

from app.domain.knowledge import Article, ArticlePage, ArticleSummary
from app.domain.screening import (
    AnswerReceipt,
    ScreeningResult,
    ScreeningSession,
    ScreeningSurvey,
    SubmitAnswerRequest,
)

MOCK_SCREENING_ID = UUID("11111111-1111-4111-8111-111111111111")
SURVEY = ScreeningSurvey.model_validate_json(
    files("app").joinpath("fixtures/screening_survey.json").read_text(encoding="utf-8")
)
MOCK_PDF = files("app").joinpath("fixtures/screening.pdf").read_bytes()
ARTICLE = Article(
    slug="about-screening",
    title="О скрининге",
    summary="Демонстрационная статья базы знаний.",
    body="Это макет статьи для разработки интерфейса, а не медицинская рекомендация.",
)


class MockScreeningService:
    async def start(self, survey_id: str) -> ScreeningSession | None:
        if survey_id != SURVEY.id:
            return None
        return ScreeningSession(
            id=MOCK_SCREENING_ID, status="in_progress", survey=SURVEY.model_copy(deep=True),
        )

    async def submit_answer(
        self, screening_id: UUID, answer: SubmitAnswerRequest,
    ) -> AnswerReceipt | None:
        if screening_id != MOCK_SCREENING_ID:
            return None
        return AnswerReceipt(screening_id=screening_id, answer=answer, status="in_progress")

    async def get_results(self, screening_id: UUID) -> ScreeningResult | None:
        if screening_id != MOCK_SCREENING_ID:
            return None
        return ScreeningResult(
            screening_id=screening_id,
            survey_id=SURVEY.id,
            weights_version=SURVEY.weights_version,
            status="completed",
            score=0,
            risk_level="low",
            red_flag=False,
            disclaimer="Mock result only; no answers were evaluated. Not medical advice.",
        )

    async def get_pdf(self, screening_id: UUID) -> bytes | None:
        return MOCK_PDF if screening_id == MOCK_SCREENING_ID else None


class MockKnowledgeBaseService:
    async def list_articles(self, limit: int, offset: int) -> ArticlePage:
        summaries = [ArticleSummary(**ARTICLE.model_dump())]
        return ArticlePage(
            items=summaries[offset:offset + limit], total=len(summaries), limit=limit, offset=offset,
        )

    async def get_article(self, slug: str) -> Article | None:
        return ARTICLE.model_copy() if slug == ARTICLE.slug else None
