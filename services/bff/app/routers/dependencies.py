from app.domain.interfaces import KnowledgeBaseService, ScreeningService
from app.mocks import MockKnowledgeBaseService, MockScreeningService


def get_screening_service() -> ScreeningService:
    return MockScreeningService()


def get_knowledge_base_service() -> KnowledgeBaseService:
    return MockKnowledgeBaseService()
