import uuid

import psycopg
import pytest


def test_rejects_chunk_for_nonexistent_article_version(app_cursor):
    with pytest.raises(psycopg.errors.ForeignKeyViolation):
        app_cursor.execute(
            "INSERT INTO article_chunks (article_id, version, chunk_index, content) "
            "VALUES (999, 1, 0, 'text')",
        )


def test_rejects_duplicate_chunk_index_for_same_article_version(app_cursor, article_chunk):
    with pytest.raises(psycopg.errors.UniqueViolation):
        app_cursor.execute(
            "INSERT INTO article_chunks (article_id, version, chunk_index, content) "
            "VALUES (1, 1, 0, 'duplicate index')",
        )


def test_rejects_embedding_for_nonexistent_chunk(app_cursor):
    with pytest.raises(psycopg.errors.ForeignKeyViolation):
        app_cursor.execute(
            "INSERT INTO chunk_embeddings (chunk_id, model, embedding) VALUES (999999, 'test', %s)",
            ([0.1, 0.2],),
        )


def test_rejects_generation_for_unprojected_result(app_cursor):
    with pytest.raises(psycopg.errors.ForeignKeyViolation):
        app_cursor.execute(
            "INSERT INTO generations (result_id, result_version, owner_subject_id) VALUES (%s, 1, %s)",
            (str(uuid.uuid4()), str(uuid.uuid4())),
        )


def test_accepts_generation_for_projected_result(app_cursor, result_projection):
    result_id, version = result_projection
    app_cursor.execute(
        "INSERT INTO generations (result_id, result_version, owner_subject_id) VALUES (%s, %s, %s) RETURNING id",
        (result_id, version, str(uuid.uuid4())),
    )
    assert app_cursor.fetchone() is not None
