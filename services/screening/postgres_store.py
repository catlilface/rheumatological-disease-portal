"""PostgreSQL implementation of Screening's transactional storage."""

from __future__ import annotations

import json
import os
from collections.abc import Callable
from contextlib import closing, contextmanager
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID

from contracts.events.v1.screening_pb2 import ScreeningEvent
from pg8000.dbapi import Connection, connect

if __package__:
    from .rules import RuleConfigError, load_rules, validate_rules
    from .scoring import Recommendation, RedFlagMatch, ScoredAnswer, ScreeningCalculation
    from .storage import (
        OperationReservation, QuestionnaireVersion, ResultSnapshotUnavailable,
        SavedAnswer, ScreeningStore, StoredOperation, StoredResult, StoredSession,
    )
else:
    from rules import RuleConfigError, load_rules, validate_rules
    from scoring import Recommendation, RedFlagMatch, ScoredAnswer, ScreeningCalculation
    from storage import (
        OperationReservation, QuestionnaireVersion, ResultSnapshotUnavailable,
        SavedAnswer, ScreeningStore, StoredOperation, StoredResult, StoredSession,
    )


def connect_screening() -> Connection:
    return connect(
        host=os.environ["PGHOST"], port=5432, database="mis_screening",
        user="mis_screening_app", timeout=4,
        password=Path("/run/secrets/db-password").read_text(encoding="utf-8").strip(),
    )


def _uuid7(value: str) -> UUID | None:
    try:
        parsed = UUID(value)
    except ValueError:
        return None
    return parsed if parsed.version == 7 and str(parsed) == value else None


def _read_result(row) -> StoredResult | None:
    if row is None:
        return None
    result_id, version, session_id, subject_id, snapshot = row
    try:
        values = dict(snapshot)
        disclaimer = values.pop("disclaimer")
        created_at = datetime.fromisoformat(values.pop("created_at"))
        values["level"] = values["level"].lower()
        if values["matched_range"] is not None:
            values["matched_range"] = tuple(values["matched_range"])
        values["missing_required"] = tuple(values["missing_required"])
        values["contributing_answers"] = tuple(ScoredAnswer(**a) for a in values["contributing_answers"])
        values["red_flags"] = tuple(RedFlagMatch(**flag) for flag in values["red_flags"])
        values["recommendations"] = tuple(Recommendation(**item) for item in values["recommendations"])
        calculation = ScreeningCalculation(**values)
    except (AttributeError, KeyError, TypeError, ValueError) as exc:
        raise ResultSnapshotUnavailable(str(subject_id)) from exc
    return StoredResult(
        str(result_id), version, str(session_id), str(subject_id),
        disclaimer, created_at, calculation,
    )


class PostgresScreeningStore(ScreeningStore):
    def __init__(self, connect_database: Callable[[], Connection]):
        self._connect = connect_database

    def accepts_identifiers(self, *identifiers: str) -> bool:
        return all(_uuid7(value) is not None for value in identifiers)

    @contextmanager
    def transaction(self):
        with closing(self._connect()) as connection, closing(connection.cursor()) as cursor:
            try:
                yield _PostgresTransaction(cursor)
                connection.commit()
            except BaseException:
                connection.rollback()
                raise

    def publish(self, path: str | Path, *, disclaimer_version: str, disclaimer: str) -> None:
        definition = load_rules(path)
        version = definition["weights_version"]
        if not disclaimer_version.strip() or not disclaimer.strip():
            raise RuleConfigError(version, "$.disclaimer", "published rules require a versioned disclaimer")
        if definition.pop("disclaimer", disclaimer) != disclaimer:
            raise RuleConfigError(version, "$.disclaimer", "definition and publication disclaimer differ")
        with self.transaction() as transaction:
            transaction.publish_questionnaire(definition, disclaimer_version, disclaimer)


class _PostgresTransaction:
    def __init__(self, cursor):
        self.cursor = cursor

    def _one(self, query, args):
        self.cursor.execute(query, args)
        return self.cursor.fetchone()

    def publish_questionnaire(self, definition: dict, disclaimer_version: str, disclaimer: str) -> None:
        survey = definition["id"]
        version = definition["weights_version"]
        self.cursor.execute("SELECT pg_advisory_xact_lock(3303, hashtext(%s))", (survey,))
        self.cursor.execute(
            """
            SELECT weights_version, disclaimer_version, definition
              FROM questionnaire_versions
             WHERE survey_code=%s AND (weights_version=%s OR disclaimer_version=%s)
            """,
            (survey, version, disclaimer_version),
        )
        already_published = False
        for saved_version, saved_disclaimer_version, document in self.cursor.fetchall():
            saved_rules = dict(document)
            saved_disclaimer = saved_rules.pop("disclaimer", None)
            if saved_version == version:
                if json.dumps(saved_rules, sort_keys=True) != json.dumps(definition, sort_keys=True):
                    raise RuleConfigError(version, "$.weights_version", "published rules require a new version")
            if saved_disclaimer_version == disclaimer_version and saved_disclaimer != disclaimer:
                raise RuleConfigError(version, "$.disclaimer", "published wording requires a new disclaimer version")
            if (saved_version, saved_disclaimer_version) == (version, disclaimer_version):
                already_published = True
        if not already_published:
            self.cursor.execute(
                """
                INSERT INTO questionnaire_versions(survey_code, weights_version, disclaimer_version, definition)
                VALUES (%s, %s, %s, %s::jsonb)
                """,
                (survey, version, disclaimer_version, json.dumps({**definition, "disclaimer": disclaimer})),
            )

    def get_questionnaire(
        self, survey_id: str, version: str | None = None, disclaimer_version: str | None = None,
    ) -> QuestionnaireVersion:
        clauses = ["survey_code=%s"]
        params = [survey_id]
        if version is not None:
            clauses.append("weights_version=%s")
            params.append(version)
        if disclaimer_version is not None:
            clauses.append("disclaimer_version=%s")
            params.append(disclaimer_version)
        if any("\x00" in value for value in params):
            raise KeyError((survey_id, version, disclaimer_version))
        row = self._one(
            "SELECT weights_version, disclaimer_version, definition FROM questionnaire_versions WHERE "
            + " AND ".join(clauses) + " ORDER BY id DESC LIMIT 1",
            tuple(params),
        )
        if row is None:
            raise KeyError((survey_id, version, disclaimer_version))
        selected_version, selected_disclaimer_version, document = row
        rules = dict(document)
        disclaimer = rules.pop("disclaimer", None)
        if not isinstance(disclaimer, str) or not disclaimer.strip():
            raise RuleConfigError(selected_version, "$.disclaimer", "published disclaimer is missing")
        if rules.get("id") != survey_id:
            raise RuleConfigError(selected_version, "$.id", "definition does not match the published survey")
        if rules.get("weights_version") != selected_version:
            raise RuleConfigError(selected_version, "$.weights_version", "definition does not match the published version")
        return QuestionnaireVersion(validate_rules(rules), selected_disclaimer_version, disclaimer)

    def lock_command(self, command_id: str, operation_id: str) -> None:
        # Distinct namespaces and fixed acquisition order also cover absent rows.
        self.cursor.execute("SELECT pg_advisory_xact_lock(3301, hashtext(%s))", (command_id,))
        self.cursor.execute("SELECT pg_advisory_xact_lock(3302, hashtext(%s))", (operation_id,))

    def get_session(self, session_id: str, *, for_update: bool = False) -> StoredSession | None:
        identifier = _uuid7(session_id)
        if identifier is None:
            return None
        if for_update:
            # Read answers with a fresh snapshot after any concurrent writer commits.
            if self._one("SELECT id FROM screening_sessions WHERE id=%s FOR UPDATE", (identifier,)) is None:
                return None
        row = self._one(
            """
            SELECT s.owner_id, q.survey_code, q.weights_version, q.definition->>'disclaimer',
                   q.disclaimer_version, s.disclaimer_accepted_at, s.started_at, s.version,
                   s.status, s.final_result_id,
                   COALESCE((
                       SELECT i.outcome->'screening'->'session'
                         FROM inbox_messages AS i
                        WHERE (i.outcome->'screening'->'session')
                              @> jsonb_build_object('id', s.id::text, 'version', s.version)
                        LIMIT 1
                   ), '{}'::jsonb),
                   COALESCE((
                       SELECT jsonb_object_agg(a.question_code, jsonb_build_array(a.value, a.weighted_score))
                         FROM screening_answers AS a WHERE a.session_id=s.id
                   ), '{}'::jsonb)
              FROM screening_sessions AS s
              JOIN questionnaire_versions AS q ON q.id=s.questionnaire_version_id
             WHERE s.id=%s
            """,
            (identifier,),
        )
        if row is None:
            return None
        (subject, survey, version, disclaimer, disclaimer_version, accepted_at, started_at,
         session_version, status, final_result_id, state, answers) = row
        completed_at = state.get("completed_at")
        return StoredSession(
            session_id=session_id, subject_id=str(subject), survey_id=survey, weights_version=version,
            disclaimer=disclaimer, disclaimer_version=disclaimer_version, disclaimer_accepted_at=accepted_at,
            started_at=started_at, version=session_version, status=status,
            completed_at=datetime.fromisoformat(completed_at) if completed_at else None,
            interrupted_by_red_flag=state.get("interrupted_by_red_flag", False),
            final_result_id=str(final_result_id) if final_result_id else None,
            answers={code: SavedAnswer(value, weight) for code, (value, weight) in answers.items()},
        )

    def put_session(self, session: StoredSession) -> None:
        if session.version == 1:
            self.cursor.execute(
                """
                INSERT INTO screening_sessions(id, owner_id, questionnaire_version_id,
                                               disclaimer_accepted_at, started_at)
                SELECT %s, %s, id, %s, %s FROM questionnaire_versions
                 WHERE survey_code=%s AND weights_version=%s AND disclaimer_version=%s
                """,
                (UUID(session.session_id), UUID(session.subject_id), session.disclaimer_accepted_at,
                 session.started_at, session.survey_id, session.weights_version, session.disclaimer_version),
            )
        else:
            self.cursor.execute(
                """
                UPDATE screening_sessions
                   SET version=%s, status=%s, final_result_id=%s
                 WHERE id=%s AND version=%s
                """,
                (session.version, session.status,
                 UUID(session.final_result_id) if session.final_result_id else None,
                 UUID(session.session_id), session.version - 1),
            )
        if self.cursor.rowcount != 1:
            raise RuntimeError("Expected one session version to be written")

    def put_answer(self, session_id: str, question_code: str, answer: SavedAnswer) -> None:
        self.cursor.execute(
            """
            INSERT INTO screening_answers(session_id, question_code, value, weighted_score)
            VALUES (%s, %s, %s::jsonb, %s)
            ON CONFLICT (session_id, question_code)
            DO UPDATE SET value=excluded.value, weighted_score=excluded.weighted_score
            """,
            (UUID(session_id), question_code, json.dumps(answer.value), answer.weighted_score),
        )

    def get_latest_result(self, session_id: str) -> StoredResult | None:
        identifier = _uuid7(session_id)
        if identifier is None:
            return None
        return _read_result(self._one(
            """
            SELECT r.id, r.version, r.session_id, s.owner_id, r.revisions->-1
              FROM screening_results AS r JOIN screening_sessions AS s ON s.id=r.session_id
             WHERE r.session_id=%s
            """,
            (identifier,),
        ))

    def get_result(self, result_id: str, version: int) -> StoredResult | None:
        identifier = _uuid7(result_id)
        if identifier is None or not 1 <= version <= 2_147_483_647:
            return None
        return _read_result(self._one(
            """
            SELECT r.id, %s::integer, r.session_id, s.owner_id, r.revisions->(%s::integer - 1)
              FROM screening_results AS r JOIN screening_sessions AS s ON s.id=r.session_id
             WHERE r.id=%s AND r.version >= %s
            """,
            (version, version, identifier, version),
        ))

    def put_result(self, result: StoredResult) -> None:
        snapshot = asdict(result.calculation)
        snapshot["level"] = result.calculation.level.upper()
        snapshot["disclaimer"] = result.disclaimer
        snapshot["created_at"] = result.created_at.isoformat()
        revision = json.dumps([snapshot])
        if result.version == 1:
            self.cursor.execute(
                "INSERT INTO screening_results(id, session_id, revisions) VALUES (%s, %s, %s::jsonb)",
                (UUID(result.result_id), UUID(result.session_id), revision),
            )
        else:
            self.cursor.execute(
                "UPDATE screening_results SET revisions=revisions || %s::jsonb WHERE id=%s AND version=%s",
                (revision, UUID(result.result_id), result.version - 1),
            )
        if self.cursor.rowcount != 1:
            raise RuntimeError("Expected one result revision to be written")

    def has_command(self, command_id: str) -> bool:
        identifier = _uuid7(command_id)
        return identifier is not None and self._one(
            "SELECT 1 FROM inbox_messages WHERE message_id=%s", (identifier,),
        ) is not None

    def get_operation(self, operation_id: str) -> StoredOperation | OperationReservation | None:
        identifier = _uuid7(operation_id)
        if identifier is None:
            return None
        row = self._one(
            """
            SELECT message_id, outcome->'screening'->'operations'->(%s::text)
              FROM inbox_messages
             WHERE operation_id=%s
                OR (jsonb_typeof(outcome->'screening'->'operations')='object'
                    AND (outcome->'screening'->'operations') ? %s)
             ORDER BY 2 DESC NULLS LAST, message_id
             LIMIT 1
            """,
            (operation_id, identifier, operation_id),
        )
        if row is None:
            return None
        command_id, outcome = row
        if not isinstance(outcome, dict):
            return OperationReservation(str(command_id))
        return StoredOperation(
            operation_id, str(command_id), outcome["subject_id"],
            bytes.fromhex(outcome["fingerprint"]), bytes.fromhex(outcome["response"]),
        )

    def put_operation(self, operation: StoredOperation, *, session: StoredSession | None = None) -> None:
        command_id = UUID(operation.command_id)
        row = self._one(
            "SELECT outcome FROM inbox_messages WHERE message_id=%s FOR UPDATE",
            (command_id,),
        )
        existing = row[0] if row is not None else None
        old_screening = existing.get("screening") if isinstance(existing, dict) else None
        if isinstance(existing, dict) and (
            "screening" not in existing
            or (isinstance(old_screening, dict) and isinstance(old_screening.get("operations"), dict))
        ):
            outcome = existing
        elif existing is None:
            outcome = {}
        else:
            outcome = {"legacy_outcome": existing}
        screening = outcome.setdefault("screening", {})
        screening.setdefault("operations", {})[operation.operation_id] = {
            "subject_id": operation.subject_id,
            "fingerprint": operation.fingerprint.hex(),
            "response": operation.response.hex(),
        }
        if session is not None:
            screening["session"] = {
                "id": session.session_id,
                "version": session.version,
                "completed_at": session.completed_at.isoformat() if session.completed_at else None,
                "interrupted_by_red_flag": session.interrupted_by_red_flag,
            }
        if row is None:
            self.cursor.execute(
                "INSERT INTO inbox_messages(message_id, operation_id, outcome) VALUES (%s, %s, %s::jsonb)",
                (command_id, UUID(operation.operation_id), json.dumps(outcome)),
            )
        else:
            self.cursor.execute(
                "UPDATE inbox_messages SET outcome=%s::jsonb WHERE message_id=%s",
                (json.dumps(outcome), command_id),
            )

    def append_event(self, event: bytes) -> None:
        metadata = ScreeningEvent.FromString(event).metadata
        self.cursor.execute(
            """
            INSERT INTO outbox_events(event_id, source, entity_type, entity_id, entity_version,
                                      schema_version, operation_id, causation_id, correlation_id,
                                      occurred_at, payload)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (UUID(metadata.event_id), metadata.source, metadata.entity_type, UUID(metadata.entity_id),
             metadata.entity_version, metadata.schema_version, UUID(metadata.operation_id),
             UUID(metadata.causation_id), UUID(metadata.correlation_id), metadata.occurred_at.ToDatetime(tzinfo=UTC), event),
        )
