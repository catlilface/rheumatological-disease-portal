"""Confirms migrations actually produced what app/database/models.py claims.

There is no independent reference document for this schema (see README for
where the table list came from), so this checks the ORM metadata against the
live, migrated database rather than against a frozen spec text.
"""


def test_migrated_tables_match_orm_metadata(app_cursor):
    import app.database.models as models

    app_cursor.execute(
        "SELECT table_name FROM information_schema.tables WHERE table_schema = 'public'",
    )
    actual = {row[0] for row in app_cursor.fetchall()} - {"alembic_version"}
    expected = set(models.Base.metadata.tables)
    assert actual == expected


def test_access_audit_has_no_foreign_keys(app_cursor):
    app_cursor.execute(
        "SELECT count(*) FROM information_schema.table_constraints "
        "WHERE table_name = 'access_audit' AND constraint_type = 'FOREIGN KEY'",
    )
    assert app_cursor.fetchone() == (0,)
