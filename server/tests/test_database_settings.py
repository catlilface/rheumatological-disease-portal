import pytest
from pydantic import ValidationError


def test_application_settings_can_be_loaded_without_database_password():
    from app.settings import Settings

    settings = Settings(_env_file=None)
    assert settings.database.host == "localhost"
    assert settings.database.port == 5432
    assert settings.database.name == "rheumatology"
    assert settings.database.user == "rheumatology"
    assert settings.database.password.get_secret_value() == ""


def test_nested_database_settings_load_from_dotenv(tmp_path):
    from app.settings import Settings

    env_file = tmp_path / ".env"
    env_file.write_text(
        "DATABASE__HOST=db.example.test\nDATABASE__PORT=5433\n"
        "DATABASE__NAME=portal_test\nDATABASE__USER=test_user\n"
        "DATABASE__PASSWORD=synthetic-test-password\nDATABASE__CONNECT_TIMEOUT=2\n",
        encoding="utf-8",
    )
    database = Settings(_env_file=env_file).database
    assert database.host == "db.example.test"
    assert database.port == 5433
    assert database.name == "portal_test"
    assert database.user == "test_user"
    assert database.password.get_secret_value() == "synthetic-test-password"
    assert database.connect_timeout == 2


def test_environment_overrides_database_fields_without_losing_dotenv_values(tmp_path, monkeypatch):
    from app.settings import Settings

    env_file = tmp_path / ".env"
    env_file.write_text(
        "DATABASE__HOST=file-db\nDATABASE__PORT=5432\nDATABASE__NAME=file_db\n"
        "DATABASE__PASSWORD=file-password\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("DATABASE__PORT", "5433")
    monkeypatch.setenv("DATABASE__PASSWORD", "environment-password")
    database = Settings(_env_file=env_file).database
    assert database.port == 5433
    assert database.password.get_secret_value() == "environment-password"
    assert database.host == "file-db"
    assert database.name == "file_db"


def test_connection_url_preserves_special_characters():
    from app.database.settings import DatabaseSettings
    from sqlalchemy.engine import make_url

    password = "synthetic:@/?#% password"
    database = DatabaseSettings(
        host="localhost", port=5433, name="portal test", user="user@example", password=password,
    )
    url = make_url(database.connection_url().render_as_string(hide_password=False))
    assert url.drivername == "postgresql+psycopg"
    assert url.username == "user@example"
    assert url.password == password
    assert url.host == "localhost"
    assert url.port == 5433
    assert url.database == "portal test"


def test_database_password_is_hidden_in_settings_and_url_representation():
    from app.settings import Settings

    settings = Settings(_env_file=None, database={"password": "synthetic-secret"})
    assert "synthetic-secret" not in repr(settings)
    assert "synthetic-secret" not in settings.model_dump_json()
    assert "synthetic-secret" not in str(settings.database.connection_url())


def test_missing_password_prevents_engine_creation():
    from app.database.connection import create_database_engine
    from app.database.settings import DatabaseSettings

    with pytest.raises(ValueError, match="DATABASE__PASSWORD"):
        create_database_engine(DatabaseSettings())


def test_engine_construction_does_not_connect_to_database():
    from app.database.connection import create_database_engine
    from app.database.settings import DatabaseSettings

    # No database is listening on this port; construction must remain lazy.
    engine = create_database_engine(DatabaseSettings(
        host="127.0.0.1", port=1, name="unreachable", password="synthetic-password",
    ))
    try:
        assert engine.url.drivername == "postgresql+psycopg"
        assert engine.url.database == "unreachable"
    finally:
        engine.dispose()


@pytest.mark.parametrize("values", [
    {"port": 0}, {"port": 65536}, {"connect_timeout": 0},
    {"host": ""}, {"name": ""}, {"user": ""},
])
def test_invalid_database_connection_settings_are_rejected(values):
    from app.database.settings import DatabaseSettings

    with pytest.raises(ValidationError):
        DatabaseSettings(**values)
