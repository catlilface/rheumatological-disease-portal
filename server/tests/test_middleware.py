import importlib

import httpx
import pytest

pytestmark = pytest.mark.anyio


@pytest.fixture
def configured_app(monkeypatch):
    from app import main

    try:
        with monkeypatch.context() as environment:
            environment.setenv("ALLOWED_HOSTS", '["api.example.test"]')
            environment.setenv("CORS__ALLOW_ORIGINS", '["https://frontend.example.test"]')
            environment.setenv("CORS__ALLOW_METHODS", '["GET", "POST"]')
            environment.setenv("CORS__ALLOW_HEADERS", '["Authorization"]')
            environment.setenv("CORS__ALLOW_CREDENTIALS", "true")
            environment.setenv("CORS__EXPOSE_HEADERS", '["X-Request-ID"]')
            environment.setenv("CORS__MAX_AGE", "120")
            yield importlib.reload(main).app
    finally:
        importlib.reload(main)


@pytest.mark.parametrize("host", ["api.example.test", "api.example.test:8000"])
async def test_configured_host_accepts_health_without_origin(configured_app, host):
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=configured_app), base_url=f"http://{host}"
    ) as client:
        response = await client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


@pytest.mark.parametrize("preflight", [False, True])
async def test_untrusted_host_is_rejected_even_for_preflight(configured_app, preflight):
    headers = {"Origin": "https://frontend.example.test"}
    if preflight:
        headers["Access-Control-Request-Method"] = "GET"
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=configured_app), base_url="http://attacker.test"
    ) as client:
        response = await client.request("OPTIONS" if preflight else "GET", "/health", headers=headers)
    assert response.status_code == 400


async def test_allowed_origin_receives_cors_and_credentials_headers(configured_app):
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=configured_app), base_url="http://api.example.test"
    ) as client:
        response = await client.get("/health", headers={"Origin": "https://frontend.example.test"})
    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "https://frontend.example.test"
    assert response.headers["access-control-allow-credentials"] == "true"
    assert response.headers["access-control-expose-headers"] == "X-Request-ID"


async def test_disallowed_origin_has_no_cors_permission(configured_app):
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=configured_app), base_url="http://api.example.test"
    ) as client:
        response = await client.get("/health", headers={"Origin": "https://attacker.test"})
    # CORS controls browser access to the response, not server-side authorization.
    assert response.status_code == 200
    assert "access-control-allow-origin" not in response.headers


async def test_preflight_uses_configured_methods_headers_and_max_age(configured_app):
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=configured_app), base_url="http://api.example.test"
    ) as client:
        response = await client.options("/health", headers={
            "Origin": "https://frontend.example.test",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "Authorization",
        })
    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "https://frontend.example.test"
    assert "POST" in response.headers["access-control-allow-methods"].split(", ")
    assert "authorization" in response.headers["access-control-allow-headers"].lower()
    assert response.headers["access-control-max-age"] == "120"


@pytest.mark.parametrize("overrides", [
    {"Origin": "https://attacker.test"},
    {"Access-Control-Request-Method": "DELETE"},
    {"Access-Control-Request-Headers": "X-Not-Allowed"},
])
async def test_preflight_rejects_disallowed_origin_method_or_header(configured_app, overrides):
    headers = {
        "Origin": "https://frontend.example.test",
        "Access-Control-Request-Method": "GET",
    }
    headers.update(overrides)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=configured_app), base_url="http://api.example.test"
    ) as client:
        response = await client.options("/health", headers=headers)
    assert response.status_code == 400


async def test_default_configuration_does_not_enable_cross_origin_access():
    from app.main import app

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://localhost"
    ) as client:
        response = await client.get("/health", headers={"Origin": "https://frontend.example.test"})
    assert response.status_code == 200
    assert "access-control-allow-origin" not in response.headers
    assert "access-control-allow-credentials" not in response.headers
