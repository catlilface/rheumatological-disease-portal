import os

import psycopg
import pytest

SERVICE = "files"


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
def stored_file(app_cursor):
    import uuid

    app_cursor.execute(
        "INSERT INTO stored_files (object_key, owner_subject_id, source_service, size_bytes, checksum_sha256) "
        "VALUES (%s, %s, 'reporting', 1024, %s) RETURNING id",
        (f"reports/{uuid.uuid4()}.pdf", str(uuid.uuid4()), b"\x00" * 32),
    )
    return app_cursor.fetchone()[0]
