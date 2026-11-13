import importlib

import httpx
import pytest


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.mark.anyio
async def test_health_returns_ok_without_database():
    from app.main import app

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


@pytest.mark.parametrize("path", ["/", "/docs", "/redoc", "/openapi.json"])
@pytest.mark.anyio
async def test_other_endpoints_are_unavailable(path):
    from app.main import app

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.get(path)
        assert response.status_code == 404


def test_environment_settings_configure_application(monkeypatch):
    from app import main

    try:
        with monkeypatch.context() as environment:
            environment.setenv("APP_NAME", "Configured portal")
            environment.setenv("DEBUG", "true")
            configured = importlib.reload(main).app
            assert configured.title == "Configured portal"
            assert configured.debug is True
    finally:
        importlib.reload(main)
