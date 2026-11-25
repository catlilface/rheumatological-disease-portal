"""Transactional storage contract and a local in-memory implementation."""

from __future__ import annotations

from abc import ABC, abstractmethod
from contextlib import AbstractContextManager, contextmanager
from copy import deepcopy
from dataclasses import dataclass, field
from datetime import datetime
from threading import Lock
from typing import TYPE_CHECKING, Literal, Protocol

if TYPE_CHECKING:
    from .registry import BaseRegistry
    from .scoring import AnswerValue, ScreeningCalculation


DEMO_DISCLAIMER = "Демонстрационная анкета, не медицинская рекомендация."
DEMO_DISCLAIMER_VERSION = "demo-v1"


@dataclass(frozen=True, slots=True)
class QuestionnaireVersion:
    rules: dict
    disclaimer_version: str
    disclaimer: str


@dataclass(frozen=True, slots=True)
class SavedAnswer:
    value: AnswerValue
    weighted_score: int


@dataclass(frozen=True, slots=True)
class StoredSession:
    session_id: str
    subject_id: str
    survey_id: str
    weights_version: str
    disclaimer: str
    disclaimer_version: str
    disclaimer_accepted_at: datetime
    started_at: datetime
    version: int = 1
    status: Literal["in_progress", "completed", "abandoned"] = "in_progress"
    completed_at: datetime | None = None
    interrupted_by_red_flag: bool = False
    final_result_id: str | None = None
    answers: dict[str, SavedAnswer] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class StoredResult:
    result_id: str
    version: int
    session_id: str
    subject_id: str
    disclaimer: str
    created_at: datetime
    calculation: ScreeningCalculation


class ResultSnapshotUnavailable(ValueError):
    """A stored revision does not contain a full result snapshot."""

    def __init__(self, subject_id: str):
        self.subject_id = subject_id
        super().__init__("Stored screening result lacks a complete snapshot.")


@dataclass(frozen=True, slots=True)
class StoredOperation:
    operation_id: str
    command_id: str
    subject_id: str
    fingerprint: bytes
    response: bytes


@dataclass(frozen=True, slots=True)
class OperationReservation:
    """An older inbox entry reserves an operation ID without a saved response."""

    command_id: str


class ScreeningTransaction(Protocol):
    def get_questionnaire(
        self, survey_id: str, version: str | None = None, disclaimer_version: str | None = None,
    ) -> QuestionnaireVersion:
        """Return the exact requested version, or the current match for omitted versions."""

    def lock_command(self, command_id: str, operation_id: str) -> None:
        """Serialize duplicate command or operation IDs until commit."""

    def get_session(self, session_id: str, *, for_update: bool = False) -> StoredSession | None: ...
    def put_session(self, session: StoredSession) -> None: ...
    def put_answer(self, session_id: str, question_code: str, answer: SavedAnswer) -> None: ...
    def get_latest_result(self, session_id: str) -> StoredResult | None: ...
    def get_result(self, result_id: str, version: int) -> StoredResult | None: ...
    def put_result(self, result: StoredResult) -> None: ...
    def has_command(self, command_id: str) -> bool: ...
    def get_operation(self, operation_id: str) -> StoredOperation | OperationReservation | None: ...
    def put_operation(self, operation: StoredOperation, *, session: StoredSession | None = None) -> None:
        """Record the outcome and, on success, the session revision changed by this command."""

    def append_event(self, event: bytes) -> None: ...


class ScreeningStore(ABC):
    def accepts_identifiers(self, *identifiers: str) -> bool:
        """Whether the storage can represent an incoming set of command identifiers."""
        return True

    @abstractmethod
    def transaction(self) -> AbstractContextManager[ScreeningTransaction]:
        """Commit all writes together on success and roll them back on exception."""


@dataclass
class _State:
    sessions: dict[str, StoredSession] = field(default_factory=dict)
    latest_results: dict[str, StoredResult] = field(default_factory=dict)
    results: dict[tuple[str, int], StoredResult] = field(default_factory=dict)
    commands: dict[str, StoredOperation] = field(default_factory=dict)
    operations: dict[str, StoredOperation] = field(default_factory=dict)
    outbox: list[bytes] = field(default_factory=list)


class _MemoryTransaction:
    def __init__(self, state: _State, rules: BaseRegistry):
        self._state = state
        self._rules = rules

    def get_questionnaire(
        self, survey_id: str, version: str | None = None, disclaimer_version: str | None = None,
    ) -> QuestionnaireVersion:
        if disclaimer_version is not None and disclaimer_version != DEMO_DISCLAIMER_VERSION:
            raise KeyError(disclaimer_version)
        return QuestionnaireVersion(self._rules.get(survey_id, version), DEMO_DISCLAIMER_VERSION, DEMO_DISCLAIMER)

    def lock_command(self, command_id: str, operation_id: str) -> None:
        # The store lock already serializes all operations in this transaction.
        pass

    def get_session(self, session_id: str, *, for_update: bool = False) -> StoredSession | None:
        return deepcopy(self._state.sessions.get(session_id))

    def put_session(self, session: StoredSession) -> None:
        self._state.sessions[session.session_id] = deepcopy(session)

    def put_answer(self, session_id: str, question_code: str, answer: SavedAnswer) -> None:
        self._state.sessions[session_id].answers[question_code] = answer

    def get_latest_result(self, session_id: str) -> StoredResult | None:
        return deepcopy(self._state.latest_results.get(session_id))

    def get_result(self, result_id: str, version: int) -> StoredResult | None:
        return deepcopy(self._state.results.get((result_id, version)))

    def put_result(self, result: StoredResult) -> None:
        result = deepcopy(result)
        self._state.latest_results[result.session_id] = result
        self._state.results[result.result_id, result.version] = result

    def has_command(self, command_id: str) -> bool:
        return command_id in self._state.commands

    def get_operation(self, operation_id: str) -> StoredOperation | None:
        return self._state.operations.get(operation_id)

    def put_operation(self, operation: StoredOperation, *, session: StoredSession | None = None) -> None:
        self._state.commands.setdefault(operation.command_id, operation)
        self._state.operations[operation.operation_id] = operation

    def append_event(self, event: bytes) -> None:
        self._state.outbox.append(event)


class InMemoryScreeningStore(ScreeningStore):
    """Serialize transactions and keep only committed snapshots."""

    def __init__(self, rules: BaseRegistry):
        self._rules = rules
        self._state = _State()
        self._lock = Lock()

    @contextmanager
    def transaction(self):
        with self._lock:
            state = deepcopy(self._state)
            yield _MemoryTransaction(state, self._rules)
            self._state = state

    def outbox_events(self) -> tuple[bytes, ...]:
        with self._lock:
            return tuple(self._state.outbox)
