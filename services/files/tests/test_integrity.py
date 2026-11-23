import uuid

import psycopg
import pytest


def test_rejects_negative_size(app_cursor):
    with pytest.raises(psycopg.errors.CheckViolation):
        app_cursor.execute(
            "INSERT INTO stored_files (object_key, owner_subject_id, source_service, size_bytes, checksum_sha256) "
            "VALUES (%s, %s, 'reporting', -1, %s)",
            (f"reports/{uuid.uuid4()}.pdf", str(uuid.uuid4()), b"\x00" * 32),
        )


def test_rejects_duplicate_object_key(app_cursor):
    object_key = f"reports/{uuid.uuid4()}.pdf"
    app_cursor.execute(
        "INSERT INTO stored_files (object_key, owner_subject_id, source_service, size_bytes, checksum_sha256) "
        "VALUES (%s, %s, 'reporting', 1024, %s)",
        (object_key, str(uuid.uuid4()), b"\x00" * 32),
    )
    with pytest.raises(psycopg.errors.UniqueViolation):
        app_cursor.execute(
            "INSERT INTO stored_files (object_key, owner_subject_id, source_service, size_bytes, checksum_sha256) "
            "VALUES (%s, %s, 'reporting', 2048, %s)",
            (object_key, str(uuid.uuid4()), b"\x11" * 32),
        )


def test_rejects_grant_for_nonexistent_file(app_cursor):
    with pytest.raises(psycopg.errors.ForeignKeyViolation):
        app_cursor.execute(
            "INSERT INTO download_grants (stored_file_id, token_hash, owner_subject_id, recipient_subject_id, expires_at) "
            "VALUES (%s, %s, %s, %s, now() + interval '1 hour')",
            (str(uuid.uuid4()), b"token-hash", str(uuid.uuid4()), str(uuid.uuid4())),
        )


def test_rejects_duplicate_token_hash(app_cursor, stored_file):
    token_hash = b"same-token-hash"
    app_cursor.execute(
        "INSERT INTO download_grants (stored_file_id, token_hash, owner_subject_id, recipient_subject_id, expires_at) "
        "VALUES (%s, %s, %s, %s, now() + interval '1 hour')",
        (stored_file, token_hash, str(uuid.uuid4()), str(uuid.uuid4())),
    )
    with pytest.raises(psycopg.errors.UniqueViolation):
        app_cursor.execute(
            "INSERT INTO download_grants (stored_file_id, token_hash, owner_subject_id, recipient_subject_id, expires_at) "
            "VALUES (%s, %s, %s, %s, now() + interval '1 hour')",
            (stored_file, token_hash, str(uuid.uuid4()), str(uuid.uuid4())),
        )


def test_renewal_revokes_the_previous_grant_and_adds_a_new_version(app_cursor, stored_file):
    owner, recipient = str(uuid.uuid4()), str(uuid.uuid4())
    app_cursor.execute(
        "INSERT INTO download_grants (stored_file_id, token_hash, owner_subject_id, recipient_subject_id, "
        "version, expires_at) VALUES (%s, %s, %s, %s, 1, now() + interval '24 hours') RETURNING id",
        (stored_file, b"grant-v1", owner, recipient),
    )
    first_grant = app_cursor.fetchone()[0]
    app_cursor.execute("UPDATE download_grants SET revoked_at = now() WHERE id = %s", (first_grant,))
    app_cursor.execute(
        "INSERT INTO download_grants (stored_file_id, token_hash, owner_subject_id, recipient_subject_id, "
        "version, expires_at) VALUES (%s, %s, %s, %s, 2, now() + interval '24 hours')",
        (stored_file, b"grant-v2", owner, recipient),
    )
    app_cursor.execute(
        "SELECT version FROM download_grants WHERE stored_file_id = %s AND revoked_at IS NULL", (stored_file,),
    )
    assert app_cursor.fetchone() == (2,)
