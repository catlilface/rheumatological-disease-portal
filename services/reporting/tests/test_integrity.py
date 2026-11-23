import uuid

import psycopg
import pytest


def test_rejects_duplicate_operation_id(app_cursor):
    operation_id = str(uuid.uuid4())
    app_cursor.execute(
        "INSERT INTO report_jobs (operation_id, owner_subject_id, result_id, result_version, "
        "template_version, locale) VALUES (%s, %s, %s, 1, 'v1', 'ru')",
        (operation_id, str(uuid.uuid4()), str(uuid.uuid4())),
    )
    with pytest.raises(psycopg.errors.UniqueViolation):
        app_cursor.execute(
            "INSERT INTO report_jobs (operation_id, owner_subject_id, result_id, result_version, "
            "template_version, locale) VALUES (%s, %s, %s, 1, 'v1', 'ru')",
            (operation_id, str(uuid.uuid4()), str(uuid.uuid4())),
        )


def test_rejects_second_snapshot_for_same_job(app_cursor, report_job):
    app_cursor.execute(
        "INSERT INTO report_snapshots (report_job_id, template_version, encrypted_input) "
        "VALUES (%s, 'v1', %s)",
        (report_job, b"ciphertext"),
    )
    with pytest.raises(psycopg.errors.UniqueViolation):
        app_cursor.execute(
            "INSERT INTO report_snapshots (report_job_id, template_version, encrypted_input) "
            "VALUES (%s, 'v1', %s)",
            (report_job, b"other-ciphertext"),
        )


def test_rejects_snapshot_for_nonexistent_job(app_cursor):
    with pytest.raises(psycopg.errors.ForeignKeyViolation):
        app_cursor.execute(
            "INSERT INTO report_snapshots (report_job_id, template_version, encrypted_input) "
            "VALUES (%s, 'v1', %s)",
            (str(uuid.uuid4()), b"ciphertext"),
        )
