from uuid import UUID

import httpx
import pytest

pytestmark = pytest.mark.anyio
SURVEY_ID = "rheuma_screening_v1"


@pytest.fixture
async def client():
    from app.main import app

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://localhost"
    ) as client:
        yield client


async def start_screening(client):
    response = await client.post("/api/v1/screenings", json={"survey_id": SURVEY_ID})
    assert response.status_code == 201
    return response.json()


async def test_start_returns_session_and_survey(client):
    session = await start_screening(client)
    assert UUID(session["id"])
    assert session["status"] == "in_progress"
    assert session["survey"]["id"] == SURVEY_ID
    assert session["survey"]["blocks"][1]["questions"][0]["code"] == "В1"


@pytest.mark.parametrize("answer", [
    {"question_code": "A1", "value": True},
    {"question_code": "A1", "value": False},
    {"question_code": "A6", "value": "30-60"},
])
async def test_submit_answer_returns_mock_receipt(client, answer):
    session = await start_screening(client)
    response = await client.post(f"/api/v1/screenings/{session['id']}/answers", json=answer)
    assert response.status_code == 200
    assert response.json() == {
        "screening_id": session["id"], "answer": answer, "status": "in_progress",
    }


async def test_results_are_explicitly_mocked(client):
    session = await start_screening(client)
    response = await client.get(f"/api/v1/screenings/{session['id']}/results")
    assert response.status_code == 200
    result = response.json()
    assert result["screening_id"] == session["id"]
    assert result["survey_id"] == SURVEY_ID
    assert result["weights_version"] == "draft-v1"
    assert result["risk_level"] == "low"
    assert "mock" in result["disclaimer"].lower()


async def test_download_returns_pdf_attachment(client):
    session = await start_screening(client)
    response = await client.get(f"/api/v1/screenings/{session['id']}/pdf")
    assert response.status_code == 200
    assert response.headers["content-type"] == "application/pdf"
    assert response.headers["content-disposition"] == (
        f'attachment; filename="screening-{session["id"]}.pdf"'
    )
    assert response.content.startswith(b"%PDF-1.")
    assert response.content.rstrip().endswith(b"%%EOF")
    assert b"Mock screening report" in response.content


async def test_knowledge_base_list_and_detail(client):
    response = await client.get("/api/v1/knowledge-base/articles?limit=1&offset=0")
    assert response.status_code == 200
    page = response.json()
    assert page["total"] == 1
    assert page["limit"] == 1
    assert page["offset"] == 0
    assert len(page["items"]) == 1
    summary = page["items"][0]
    detail = await client.get(f"/api/v1/knowledge-base/articles/{summary['slug']}")
    assert detail.status_code == 200
    assert detail.json()["title"] == summary["title"]
    assert detail.json()["body"]
    empty = await client.get("/api/v1/knowledge-base/articles?offset=1")
    assert empty.json()["items"] == []
    assert empty.json()["total"] == 1


@pytest.mark.parametrize("query", ["limit=0", "limit=101", "offset=-1"])
async def test_invalid_pagination_returns_422(client, query):
    response = await client.get(f"/api/v1/knowledge-base/articles?{query}")
    assert response.status_code == 422


@pytest.mark.parametrize("body", [{}, {"survey_id": ""}])
async def test_invalid_start_returns_422(client, body):
    response = await client.post("/api/v1/screenings", json=body)
    assert response.status_code == 422


@pytest.mark.parametrize("body", [
    {}, {"question_code": "", "value": True},
    {"question_code": "A1", "value": 1}, {"question_code": "A1", "value": None},
])
async def test_invalid_answer_returns_422(client, body):
    session = await start_screening(client)
    response = await client.post(f"/api/v1/screenings/{session['id']}/answers", json=body)
    assert response.status_code == 422


@pytest.mark.parametrize("method,path,body", [
    ("POST", "/api/v1/screenings", {"survey_id": "unknown"}),
    ("GET", "/api/v1/knowledge-base/articles/unknown", None),
    ("GET", "/api/v1/screenings/00000000-0000-0000-0000-000000000000/results", None),
    ("GET", "/api/v1/screenings/00000000-0000-0000-0000-000000000000/pdf", None),
    ("POST", "/api/v1/screenings/00000000-0000-0000-0000-000000000000/answers",
     {"question_code": "A1", "value": True}),
])
async def test_unknown_resources_return_404(client, method, path, body):
    response = await client.request(method, path, json=body)
    assert response.status_code == 404
    assert isinstance(response.json()["detail"], str)


async def test_mock_does_not_persist_answers_or_change_results(client):
    session = await start_screening(client)
    path = f"/api/v1/screenings/{session['id']}"
    before = await client.get(f"{path}/results")
    answer = await client.post(f"{path}/answers", json={"question_code": "В1", "value": True})
    assert answer.status_code == 200
    after = await client.get(f"{path}/results")
    assert after.json() == before.json()
    assert (await start_screening(client)) == session


async def test_screening_service_can_be_replaced(client, monkeypatch):
    from app.main import app
    from app.mocks import MockScreeningService
    from app.routers.dependencies import get_screening_service

    class UnavailableScreeningService(MockScreeningService):
        async def start(self, survey_id):
            return None

    monkeypatch.setitem(app.dependency_overrides, get_screening_service, UnavailableScreeningService)
    response = await client.post("/api/v1/screenings", json={"survey_id": SURVEY_ID})
    assert response.status_code == 404
    assert response.json() == {"detail": "Survey not found"}


async def test_invalid_screening_id_returns_422(client):
    response = await client.get("/api/v1/screenings/not-a-uuid/results")
    assert response.status_code == 422


async def test_openapi_describes_binary_pdf_and_typed_models():
    from app.main import app

    schema = app.openapi()
    pdf = schema["paths"]["/api/v1/screenings/{screening_id}/pdf"]["get"]
    assert pdf["responses"]["200"]["content"] == {
        "application/pdf": {"schema": {"type": "string", "format": "binary"}},
    }
    assert "ScreeningSurvey" in schema["components"]["schemas"]
    assert "SubmitAnswerRequest" in schema["components"]["schemas"]
