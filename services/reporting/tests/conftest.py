import os

import psycopg
import pytest

SERVICE = "reporting"


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
def report_job(app_cursor):
    import uuid

    app_cursor.execute(
        "INSERT INTO report_jobs (operation_id, owner_subject_id, result_id, result_version, "
        "template_version, locale) VALUES (%s, %s, %s, 1, 'v1', 'ru') RETURNING id",
        (str(uuid.uuid4()), str(uuid.uuid4()), str(uuid.uuid4())),
    )
    return app_cursor.fetchone()[0]
