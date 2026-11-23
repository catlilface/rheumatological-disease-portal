"""Confirms migrations actually produced what app/database/models.py claims."""


def test_migrated_tables_match_orm_metadata(app_cursor):
    import app.database.models as models

    app_cursor.execute(
        "SELECT table_name FROM information_schema.tables WHERE table_schema = 'public'",
    )
    actual = {row[0] for row in app_cursor.fetchall()} - {"alembic_version"}
    expected = set(models.Base.metadata.tables)
    assert actual == expected
