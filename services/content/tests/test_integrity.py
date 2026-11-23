import psycopg
import pytest


def _insert_version(cursor, material_id, version, *, status="draft"):
    cursor.execute(
        "INSERT INTO material_versions (material_id, version, title, body_markdown, status) "
        "VALUES (%s, %s, 'title', 'body', %s)",
        (material_id, version, status),
    )


def test_rejects_second_published_version_of_same_material(app_cursor, material):
    _insert_version(app_cursor, material, 1, status="published")
    with pytest.raises(psycopg.errors.UniqueViolation):
        _insert_version(app_cursor, material, 2, status="published")


def test_allows_multiple_draft_versions_of_same_material(app_cursor, material):
    _insert_version(app_cursor, material, 1, status="draft")
    _insert_version(app_cursor, material, 2, status="draft")
    app_cursor.execute("SELECT count(*) FROM material_versions WHERE material_id = %s", (material,))
    assert app_cursor.fetchone() == (2,)


def test_rejects_duplicate_version_number_for_same_material(app_cursor, material):
    _insert_version(app_cursor, material, 1)
    with pytest.raises(psycopg.errors.UniqueViolation):
        _insert_version(app_cursor, material, 1)


def test_rejects_source_for_nonexistent_version(app_cursor):
    with pytest.raises(psycopg.errors.ForeignKeyViolation):
        app_cursor.execute(
            "INSERT INTO material_sources (material_version_id, title, url) VALUES (999999, 't', 'u')",
        )


def test_rejects_approving_a_version_that_does_not_exist(app_cursor, material):
    with pytest.raises(psycopg.errors.ForeignKeyViolation):
        app_cursor.execute("UPDATE materials SET approved_version = 1 WHERE id = %s", (material,))


def test_accepts_approving_an_existing_version(app_cursor, material):
    import uuid

    _insert_version(app_cursor, material, 1, status="approved")
    app_cursor.execute(
        "UPDATE materials SET approved_by = %s, approved_version = 1 WHERE id = %s", (str(uuid.uuid4()), material),
    )
    app_cursor.execute("SELECT approved_version FROM materials WHERE id = %s", (material,))
    assert app_cursor.fetchone() == (1,)
