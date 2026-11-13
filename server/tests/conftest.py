import pytest


@pytest.fixture(autouse=True)
def clear_settings_environment(monkeypatch):
    for name in ("APP_NAME", "DEBUG"):
        monkeypatch.delenv(name, raising=False)
