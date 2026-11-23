import os

import psycopg
import pytest

SERVICE = "ai"


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
def result_projection(app_cursor):
    import uuid

    result_id = str(uuid.uuid4())
    app_cursor.execute(
        "INSERT INTO result_projection (result_id, version, session_id, subject_id, "
        "block_scores, level, disclaimer) VALUES (%s, 1, %s, %s, '{}'::jsonb, 'low', 'disclaimer')",
        (result_id, str(uuid.uuid4()), str(uuid.uuid4())),
    )
    return result_id, 1


@pytest.fixture
def article_chunk(app_cursor):
    app_cursor.execute(
        "INSERT INTO article_projection (article_id, version, slug, title, status) "
        "VALUES (1, 1, 'about-ra', 'About RA', 'published')",
    )
    app_cursor.execute(
        "INSERT INTO article_chunks (article_id, version, chunk_index, content) "
        "VALUES (1, 1, 0, 'chunk text') RETURNING id",
    )
    return app_cursor.fetchone()[0]
