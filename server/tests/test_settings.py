import os
from pathlib import Path
import shutil
import subprocess
import sys

import pytest
from pydantic import ValidationError


def test_missing_env_file_uses_defaults(tmp_path):
    from app.settings import Settings

    settings = Settings(_env_file=tmp_path / "missing.env")

    assert settings.app_name == "Rheumatological Disease Portal"
    assert settings.debug is False


def test_settings_read_dotenv_and_ignore_other_services_keys(tmp_path):
    from app.settings import Settings

    env_file = tmp_path / ".env"
    env_file.write_text(
        'APP_NAME="Тестовый портал"\nDEBUG=true\nFRONTEND_PORT=3000\n',
        encoding="utf-8",
    )

    settings = Settings(_env_file=env_file)

    assert settings.app_name == "Тестовый портал"
    assert settings.debug is True


def test_environment_overrides_dotenv(tmp_path, monkeypatch):
    from app.settings import Settings

    env_file = tmp_path / ".env"
    env_file.write_text("APP_NAME=File\nDEBUG=true\n", encoding="utf-8")
    monkeypatch.setenv("APP_NAME", "Environment")
    monkeypatch.setenv("DEBUG", "false")

    settings = Settings(_env_file=env_file)

    assert settings.app_name == "Environment"
    assert settings.debug is False


def test_invalid_debug_is_rejected(monkeypatch):
    from app.settings import Settings

    monkeypatch.setenv("DEBUG", "invalid")

    with pytest.raises(ValidationError) as error:
        Settings(_env_file=None)

    assert error.value.errors()[0]["loc"] == ("debug",)


@pytest.mark.parametrize("working_directory", [".", "server"])
def test_root_dotenv_is_loaded_regardless_of_working_directory(
    tmp_path, working_directory
):
    # Use an isolated checkout so the developer's real .env is never touched.
    source = Path(__file__).resolve().parents[1] / "app"
    shutil.copytree(source, tmp_path / "server" / "app")
    (tmp_path / ".env").write_text(
        "APP_NAME=Root settings\nDEBUG=true\n", encoding="utf-8"
    )
    (tmp_path / "server" / ".env").write_text(
        "APP_NAME=Wrong settings\nDEBUG=false\n", encoding="utf-8"
    )
    environment = os.environ.copy()
    environment["PYTHONPATH"] = str(tmp_path / "server")

    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "from app.settings import Settings; "
            "s = Settings(); print(s.app_name); print(s.debug)",
        ],
        cwd=tmp_path / working_directory,
        env=environment,
        capture_output=True,
        text=True,
        check=True,
    )

    assert result.stdout.splitlines() == ["Root settings", "True"]
