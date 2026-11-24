"""Apply Screening commands and write v1 result events in one transaction."""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime
from hashlib import sha256
from uuid import uuid7

from contracts.commands.v1.screening_pb2 import ScreeningCommand
from contracts.common.v1 import metadata_pb2 as metadata
from contracts.common.v1 import screening_pb2 as screening
from contracts.events.v1.screening_pb2 import ScreeningEvent

if __package__:
    from .scoring import AnswerError, ScreeningCalculation, calculate_result
    from .storage import (
        OperationReservation, ResultSnapshotUnavailable, SavedAnswer, ScreeningStore, ScreeningTransaction,
        StoredOperation, StoredResult, StoredSession,
    )
else:
    from scoring import AnswerError, ScreeningCalculation, calculate_result
    from storage import (
        OperationReservation, ResultSnapshotUnavailable, SavedAnswer, ScreeningStore, ScreeningTransaction,
        StoredOperation, StoredResult, StoredSession,
    )


LEVELS = {
    "low": screening.SCREENING_LEVEL_LOW,
    "medium": screening.SCREENING_LEVEL_MEDIUM,
    "high": screening.SCREENING_LEVEL_HIGH,
    "red_flag": screening.SCREENING_LEVEL_RED_FLAG,
}
SESSION_STATUSES = {
    "in_progress": screening.SESSION_STATUS_IN_PROGRESS,
    "completed": screening.SESSION_STATUS_COMPLETED,
    "abandoned": screening.SESSION_STATUS_ABANDONED,
}


class InvalidCommand(ValueError):
    """A command lacks the identity or metadata required to record an operation."""


class _Rejected(Exception):
    def __init__(self, code: str, message: str):
        self.code = code
        super().__init__(message)


def _fingerprint(command: ScreeningCommand) -> bytes:
    copy = ScreeningCommand()
    copy.CopyFrom(command)
    copy.DiscardUnknownFields()
    copy.metadata.ClearField("issued_at")
    copy.metadata.ClearField("correlation_id")
    return sha256(copy.SerializeToString(deterministic=True)).digest()


def _scored_answer(code, value, weighted_score):
    scored = screening.ScoredAnswer(weighted_score=weighted_score)
    scored.answer.question_code = code
    if isinstance(value, bool):
        scored.answer.boolean_value = value
    else:
        scored.answer.choice_value = value
    return scored


def session_message(session: StoredSession) -> screening.ScreeningSession:
    message = screening.ScreeningSession(
        session_id=session.session_id,
        subject_id=session.subject_id,
        version=session.version,
        status=SESSION_STATUSES[session.status],
        interrupted_by_red_flag=session.interrupted_by_red_flag,
    )
    message.survey.survey_id = session.survey_id
    message.survey.weights_version = session.weights_version
    message.started_at.FromDatetime(session.started_at)
    if session.completed_at is not None:
        message.completed_at.FromDatetime(session.completed_at)
    message.answers.extend(
        _scored_answer(code, answer.value, answer.weighted_score)
        for code, answer in session.answers.items()
    )
    return message


def result_message(result: StoredResult) -> screening.ScreeningResult:
    calculation = result.calculation
    message = screening.ScreeningResult(
        session_id=result.session_id,
        subject_id=result.subject_id,
        block_scores=calculation.block_scores,
        scoring_complete=calculation.scoring_complete,
        red_flag_codes=[flag.code for flag in calculation.red_flags],
        level=LEVELS[calculation.level],
        disclaimer=result.disclaimer,
    )
    message.reference.result_id = result.result_id
    message.reference.version = result.version
    message.survey.survey_id = calculation.survey_id
    message.survey.weights_version = calculation.weights_version
    if calculation.total_score is not None:
        message.total_score = calculation.total_score
    message.created_at.FromDatetime(result.created_at)
    message.contributing_answers.extend(
        _scored_answer(answer.question_code, answer.value, answer.weighted_score)
        for answer in calculation.contributing_answers
    )
    for recommendation in calculation.recommendations:
        message.recommendations.add(code=recommendation.code, text=recommendation.text)
    return message


def _event_for_result(result: StoredResult, command_meta, now: datetime) -> bytes:
    event = ScreeningEvent()
    event.metadata.event_id = str(uuid7())
    event.metadata.schema_version = 1
    event.metadata.source = "screening"
    event.metadata.entity_type = "screening_result"
    event.metadata.entity_id = result.result_id
    event.metadata.entity_version = result.version
    event.metadata.operation_id = command_meta.operation_id
    event.metadata.causation_id = command_meta.command_id
    correlation = command_meta.correlation_id
    event.metadata.correlation_id = correlation if correlation.strip() else command_meta.operation_id
    event.metadata.occurred_at.FromDatetime(now)
    event.result_changed.result.CopyFrom(result_message(result))
    return event.SerializeToString(deterministic=True)


def _reject(operation, code: str, message: str):
    operation.state = metadata.OPERATION_STATE_REJECTED
    operation.error.code = code
    operation.error.message = message
    return operation


class ScreeningWorkflow:
    def __init__(self, storage: ScreeningStore):
        self.storage = storage

    def execute(self, command: ScreeningCommand) -> metadata.Operation:
        action = command.WhichOneof("payload")
        info = command.metadata
        subject = info.actor.subject_id
        if (
            not action or info.schema_version != 1
            or not info.command_id.strip() or not info.operation_id.strip()
            or not subject.strip() or not info.actor.session_id.strip()
            or not info.HasField("issued_at")
        ):
            raise InvalidCommand("Missing or unsupported command metadata or payload")
        correlation = info.correlation_id if info.correlation_id.strip() else info.operation_id
        if not self.storage.accepts_identifiers(info.command_id, info.operation_id, subject, correlation):
            raise InvalidCommand("Invalid persisted command identifiers")

        fingerprint = _fingerprint(command)
        now = datetime.now(UTC)
        operation = metadata.Operation(operation_id=info.operation_id)
        operation.created_at.FromDatetime(now)
        operation.updated_at.CopyFrom(operation.created_at)

        with self.storage.transaction() as transaction:
            transaction.lock_command(info.command_id, info.operation_id)
            existing = transaction.get_operation(info.operation_id)
            if isinstance(existing, OperationReservation):
                if existing.command_id == info.command_id:
                    return _reject(operation, "OPERATION_OUTCOME_UNAVAILABLE", "Original outcome is unavailable.")
                return _reject(operation, "OPERATION_ID_CONFLICT", "Operation ID is already in use.")
            if existing is not None:
                if existing.fingerprint == fingerprint:
                    return metadata.Operation.FromString(existing.response)
                if existing.command_id == info.command_id:
                    return _reject(operation, "COMMAND_ID_CONFLICT", "Command ID is already in use.")
                return _reject(operation, "OPERATION_ID_CONFLICT", "Operation ID is already in use.")

            session = None
            try:
                if transaction.has_command(info.command_id):
                    raise _Rejected("COMMAND_ID_CONFLICT", "Command ID is already in use.")
                session, result = self._apply(transaction, action, command, now)
            except _Rejected as exc:
                _reject(operation, exc.code, str(exc))
            except ResultSnapshotUnavailable as exc:
                _reject(operation, "RESULT_SNAPSHOT_UNAVAILABLE", str(exc))
            else:
                operation.state = metadata.OPERATION_STATE_SUCCEEDED
                operation.resources.add(
                    resource_type="screening_session",
                    resource_id=session.session_id,
                    version=session.version,
                )
                if result is not None:
                    operation.resources.add(
                        resource_type="screening_result",
                        resource_id=result.result_id,
                        version=result.version,
                    )
            transaction.put_operation(StoredOperation(
                info.operation_id, info.command_id, subject, fingerprint, operation.SerializeToString(),
            ), session=session)
        return operation

    def _apply(self, transaction: ScreeningTransaction, action, command, now):
        info = command.metadata
        if action == "start":
            return self._start(transaction, command.start, info.actor.subject_id, now), None

        request = getattr(command, action)
        session = transaction.get_session(request.session_id, for_update=True)
        if session is None:
            raise _Rejected("SESSION_NOT_FOUND", "Screening session was not found.")
        if session.subject_id != info.actor.subject_id:
            raise _Rejected("ACCESS_DENIED", "Screening session access denied.")
        if not request.expected_session_version or request.expected_session_version != session.version:
            raise _Rejected("SESSION_VERSION_CONFLICT", "Screening session version is out of date.")
        if session.status != "in_progress":
            raise _Rejected("SESSION_NOT_IN_PROGRESS", "Screening session is already closed.")
        session = replace(session, version=session.version + 1)

        if action == "save_answer":
            return self._save_answer(transaction, session, request.answer, info, now)
        if action == "complete":
            return self._complete(transaction, session, info, now)
        if action == "continue_after_red_flag":
            if not session.interrupted_by_red_flag:
                raise _Rejected("SESSION_NOT_INTERRUPTED", "Screening session is not interrupted.")
            session = replace(session, interrupted_by_red_flag=False)
        elif action == "abandon":
            session = replace(session, status="abandoned", interrupted_by_red_flag=False)
        transaction.put_session(session)
        return session, None

    def _start(self, transaction, request, subject, now):
        survey = request.survey
        if not survey.survey_id or not survey.weights_version:
            raise _Rejected("RULES_VERSION_REQUIRED", "An exact survey version is required.")
        if (
            not request.disclaimer_accepted or not request.disclaimer_version.strip()
            or not request.HasField("disclaimer_accepted_at")
        ):
            raise _Rejected("DISCLAIMER_REQUIRED", "Current disclaimer acceptance is required.")
        try:
            questionnaire = transaction.get_questionnaire(survey.survey_id, survey.weights_version)
        except KeyError as exc:
            raise _Rejected("RULES_NOT_FOUND", "Survey version was not found.") from exc
        if request.disclaimer_version != questionnaire.disclaimer_version:
            raise _Rejected("DISCLAIMER_REQUIRED", "Current disclaimer acceptance is required.")
        if questionnaire.rules["scoring"]["thresholds"].keys() - LEVELS.keys():
            raise _Rejected("UNSUPPORTED_LEVEL", "Survey level is unsupported by Screening v1.")
        try:
            accepted_at = request.disclaimer_accepted_at.ToDatetime(tzinfo=UTC)
        except (ValueError, OverflowError) as exc:
            raise _Rejected("DISCLAIMER_REQUIRED", "Invalid disclaimer acceptance time.") from exc
        session = StoredSession(
            session_id=str(uuid7()),
            subject_id=subject,
            survey_id=survey.survey_id,
            weights_version=survey.weights_version,
            disclaimer=questionnaire.disclaimer,
            disclaimer_version=questionnaire.disclaimer_version,
            disclaimer_accepted_at=accepted_at,
            started_at=now,
        )
        transaction.put_session(session)
        return session

    def _save_answer(self, transaction, session, answer, info, now):
        if session.interrupted_by_red_flag:
            raise _Rejected("SESSION_INTERRUPTED", "Continue the screening session first.")
        field = answer.WhichOneof("value")
        if not field:
            raise _Rejected("INVALID_ANSWER", "An answer value is required.")
        value = getattr(answer, field)
        code = answer.question_code
        previous = transaction.get_latest_result(session.session_id)
        previous_flags = _flag_codes(previous)
        answers = {key: saved.value for key, saved in session.answers.items()}
        answers[code] = value
        rules = transaction.get_questionnaire(
            session.survey_id, session.weights_version, session.disclaimer_version,
        ).rules
        try:
            calculation = calculate_result(rules, answers, previous_red_flag_codes=previous_flags)
        except AnswerError as exc:
            raise _Rejected("INVALID_ANSWER", "Answer does not match the survey version.") from exc
        weight = next(
            (item.weighted_score for item in calculation.contributing_answers if item.question_code == code),
            0,
        )
        new_flags = any(flag.code not in previous_flags for flag in calculation.red_flags)
        session = replace(session, interrupted_by_red_flag=new_flags)
        transaction.put_session(session)
        transaction.put_answer(session.session_id, code, SavedAnswer(value, weight))
        result = None
        if new_flags:
            result = self._record_result(transaction, session, calculation, previous, now)
            transaction.append_event(_event_for_result(result, info, now))
        return session, result

    def _complete(self, transaction, session, info, now):
        previous = transaction.get_latest_result(session.session_id)
        rules = transaction.get_questionnaire(
            session.survey_id, session.weights_version, session.disclaimer_version,
        ).rules
        answers = {code: answer.value for code, answer in session.answers.items()}
        calculation = calculate_result(rules, answers, previous_red_flag_codes=_flag_codes(previous))
        if calculation.level is None:
            raise _Rejected("ANSWERS_INCOMPLETE", "Some required answers are missing.")
        result = self._record_result(transaction, session, calculation, previous, now)
        session = replace(
            session, status="completed", completed_at=now,
            interrupted_by_red_flag=False, final_result_id=result.result_id,
        )
        transaction.put_session(session)
        transaction.append_event(_event_for_result(result, info, now))
        return session, result

    def _record_result(
        self,
        transaction: ScreeningTransaction,
        session: StoredSession,
        calculation: ScreeningCalculation,
        previous: StoredResult | None,
        now: datetime,
    ) -> StoredResult:
        result = StoredResult(
            result_id=previous.result_id if previous else str(uuid7()),
            version=previous.version + 1 if previous else 1,
            session_id=session.session_id,
            subject_id=session.subject_id,
            disclaimer=session.disclaimer,
            created_at=previous.created_at if previous else now,
            calculation=calculation,
        )
        transaction.put_result(result)
        return result


def _flag_codes(result: StoredResult | None) -> set[str]:
    return {flag.code for flag in result.calculation.red_flags} if result else set()
