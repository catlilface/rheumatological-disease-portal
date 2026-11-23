import os

import psycopg
import pytest

SERVICE = "screening"


@pytest.fixture(scope="session")
def db_env():
    password_var = f"{SERVICE.upper()}_DB_PASSWORD"
    password = os.environ.get(password_var)
    if not password:
        pytest.skip(f"{password_var} is not set; run `make up` (or set it yourself) to run these tests")
    return {
        "host": os.environ.get("DATABASE__HOST", "localhost"),
        "port": int(os.environ.get("DATABASE__PORT", "5432")),
        "dbname": f"{SERVICE}",
        "user": f"app_{SERVICE}",
        "password": password,
    }


@pytest.fixture
def app_cursor(db_env):
    """A cursor using the service's own least-privilege role; always rolled back."""
    conn = psycopg.connect(**db_env)
    try:
        with conn.cursor() as cursor:
            yield cursor
    finally:
        conn.rollback()
        conn.close()


@pytest.fixture
def questionnaire_version(app_cursor):
    """Insert the frozen survey version a screening_session needs to reference."""
    app_cursor.execute(
        "INSERT INTO questionnaire_versions (survey_id, weights_version, definition, "
        "disclaimer, disclaimer_version) VALUES ('rheuma_screening_v1', 'draft-v1', "
        "'{}'::jsonb, 'disclaimer text', 'v1')",
    )
    return ("rheuma_screening_v1", "draft-v1")


@pytest.fixture
def screening_session(app_cursor, questionnaire_version):
    import uuid

    survey_id, weights_version = questionnaire_version
    app_cursor.execute(
        "INSERT INTO screening_sessions (session_token, owner_subject_id, survey_id, weights_version) "
        "VALUES (%s, %s, %s, %s) RETURNING id",
        (str(uuid.uuid4()), str(uuid.uuid4()), survey_id, weights_version),
    )
    return app_cursor.fetchone()[0]
