import os

import pytest


@pytest.fixture(autouse=True)
def clear_settings_environment(monkeypatch):
    from app.settings import Settings

    # Tests with explicit _env_file and isolated-checkout subprocesses still read their fixtures.
    monkeypatch.setitem(Settings.model_config, "env_file", None)
    for name in tuple(os.environ):
        if name in {"APP_NAME", "DEBUG", "ALLOWED_HOSTS", "CORS", "DATABASE"} or name.startswith(("CORS_", "DATABASE__")):
            monkeypatch.delenv(name, raising=False)


@pytest.fixture
def anyio_backend():
    return "asyncio"
