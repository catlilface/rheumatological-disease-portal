import uuid

import psycopg
import pytest


def _insert_result(cursor, session_id, *, level="low"):
    cursor.execute(
        "INSERT INTO screening_results (session_id, block_scores, level) "
        "VALUES (%s, '{}'::jsonb, %s)",
        (session_id, level),
    )


def test_rejects_answer_for_nonexistent_session(app_cursor):
    with pytest.raises(psycopg.errors.ForeignKeyViolation):
        app_cursor.execute(
            "INSERT INTO screening_answers (session_id, question_code, value, weighted_score) "
            "VALUES (%s, 'A1', 'true'::jsonb, 1)",
            (str(uuid.uuid4()),),
        )


def test_rejects_second_answer_for_same_question_as_duplicate_insert(app_cursor, screening_session):
    app_cursor.execute(
        "INSERT INTO screening_answers (session_id, question_code, value, weighted_score) "
        "VALUES (%s, 'A1', 'true'::jsonb, 1)",
        (screening_session,),
    )
    with pytest.raises(psycopg.errors.UniqueViolation):
        app_cursor.execute(
            "INSERT INTO screening_answers (session_id, question_code, value, weighted_score) "
            "VALUES (%s, 'A1', 'false'::jsonb, 0)",
            (screening_session,),
        )


def test_rejects_second_result_for_same_session(app_cursor, screening_session):
    _insert_result(app_cursor, screening_session)
    with pytest.raises(psycopg.errors.UniqueViolation):
        _insert_result(app_cursor, screening_session, level="red_flag")


def test_rejects_session_with_unregistered_survey_version(app_cursor):
    with pytest.raises(psycopg.errors.ForeignKeyViolation):
        app_cursor.execute(
            "INSERT INTO screening_sessions (session_token, owner_subject_id, survey_id, weights_version) "
            "VALUES (%s, %s, 'unknown_survey', 'v0')",
            (str(uuid.uuid4()), str(uuid.uuid4())),
        )


def test_rejects_session_without_owner_subject_id(app_cursor, questionnaire_version):
    survey_id, weights_version = questionnaire_version
    with pytest.raises(psycopg.errors.NotNullViolation):
        app_cursor.execute(
            "INSERT INTO screening_sessions (session_token, survey_id, weights_version) VALUES (%s, %s, %s)",
            (str(uuid.uuid4()), survey_id, weights_version),
        )
