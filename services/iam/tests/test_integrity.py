import psycopg
import pytest


def _insert_principal(cursor, kind, email_hash=None):
    cursor.execute(
        "INSERT INTO principals (kind, email_hash) VALUES (%s, %s) RETURNING id",
        (kind, email_hash),
    )
    return cursor.fetchone()[0]


def test_access_audit_survives_principal_deletion(app_cursor):
    principal_id = _insert_principal(app_cursor, "guest")
    app_cursor.execute(
        "INSERT INTO access_audit (actor_principal_id, subject_principal_id, action, "
        "resource_type, decision) VALUES (%s, %s, 'read', 'screening_result', 'allow')",
        (principal_id, principal_id),
    )
    app_cursor.execute("DELETE FROM principals WHERE id = %s", (principal_id,))

    app_cursor.execute(
        "SELECT decision FROM access_audit WHERE subject_principal_id = %s", (principal_id,),
    )
    assert app_cursor.fetchone() == ("allow",)


def test_auth_session_rejects_unknown_principal(app_cursor):
    import uuid

    with pytest.raises(psycopg.errors.ForeignKeyViolation):
        app_cursor.execute(
            "INSERT INTO auth_sessions (principal_id, session_token_hash, expires_at) "
            "VALUES (%s, %s, now() + interval '1 hour')",
            (str(uuid.uuid4()), b"token-hash"),
        )


def test_principal_role_rejects_unknown_role(app_cursor):
    principal_id = _insert_principal(app_cursor, "guest")
    with pytest.raises(psycopg.errors.ForeignKeyViolation):
        app_cursor.execute(
            "INSERT INTO principal_roles (principal_id, role_code) VALUES (%s, 'unknown_role')",
            (principal_id,),
        )


@pytest.mark.parametrize("kind,email_hash", [("employee", None), ("guest", b"hash")])
def test_principal_kind_email_hash_invariant_is_enforced(app_cursor, kind, email_hash):
    with pytest.raises(psycopg.errors.CheckViolation):
        _insert_principal(app_cursor, kind, email_hash)


def test_employee_with_email_hash_is_accepted(app_cursor):
    principal_id = _insert_principal(app_cursor, "employee", b"hash")
    assert principal_id is not None


def test_roles_are_seeded_and_restricted_to_mis23_values(app_cursor):
    app_cursor.execute("SELECT code FROM roles ORDER BY code")
    assert [row[0] for row in app_cursor.fetchall()] == ["admin", "editor", "patient"]
    with pytest.raises(psycopg.errors.CheckViolation):
        app_cursor.execute("INSERT INTO roles (code) VALUES ('medical_reviewer')")


def test_principal_cannot_hold_two_active_roles_at_once(app_cursor):
    principal_id = _insert_principal(app_cursor, "guest")
    app_cursor.execute(
        "INSERT INTO principal_roles (principal_id, role_code) VALUES (%s, 'patient')", (principal_id,),
    )
    with pytest.raises(psycopg.errors.UniqueViolation):
        app_cursor.execute(
            "INSERT INTO principal_roles (principal_id, role_code) VALUES (%s, 'editor')", (principal_id,),
        )


def test_revoking_a_role_allows_assigning_a_new_one(app_cursor):
    principal_id = _insert_principal(app_cursor, "guest")
    app_cursor.execute(
        "INSERT INTO principal_roles (principal_id, role_code) VALUES (%s, 'patient')", (principal_id,),
    )
    app_cursor.execute(
        "UPDATE principal_roles SET revoked_at = now() WHERE principal_id = %s AND role_code = 'patient'",
        (principal_id,),
    )
    app_cursor.execute(
        "INSERT INTO principal_roles (principal_id, role_code) VALUES (%s, 'editor')", (principal_id,),
    )
    app_cursor.execute(
        "SELECT role_code FROM principal_roles WHERE principal_id = %s AND revoked_at IS NULL", (principal_id,),
    )
    assert app_cursor.fetchone() == ("editor",)


def test_auth_session_refresh_token_is_unique(app_cursor):
    principal_id = _insert_principal(app_cursor, "guest")
    token_hash = b"shared-refresh-hash"
    app_cursor.execute(
        "INSERT INTO auth_sessions (principal_id, session_token_hash, refresh_token_hash, expires_at) "
        "VALUES (%s, %s, %s, now() + interval '168 hours')",
        (principal_id, b"session-1", token_hash),
    )
    with pytest.raises(psycopg.errors.UniqueViolation):
        app_cursor.execute(
            "INSERT INTO auth_sessions (principal_id, session_token_hash, refresh_token_hash, expires_at) "
            "VALUES (%s, %s, %s, now() + interval '168 hours')",
            (principal_id, b"session-2", token_hash),
        )
