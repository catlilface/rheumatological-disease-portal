import pytest


@pytest.fixture(autouse=True)
def clear_settings_environment(monkeypatch):
    from app.settings import Settings

    # Tests with explicit _env_file and isolated-checkout subprocesses still read their fixtures.
    monkeypatch.setitem(Settings.model_config, "env_file", None)
    for name in (
        "APP_NAME", "DEBUG", "ALLOWED_HOSTS", "CORS_ALLOW_ORIGINS",
        "CORS_ALLOW_METHODS", "CORS_ALLOW_HEADERS", "CORS_ALLOW_CREDENTIALS",
        "CORS_EXPOSE_HEADERS", "CORS_MAX_AGE",
    ):
        monkeypatch.delenv(name, raising=False)


@pytest.fixture
def anyio_backend():
    return "asyncio"
