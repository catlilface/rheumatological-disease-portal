"""Questionnaire versions, saved answers, sessions and result revisions."""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Literal

from .calculation import AnswerValue, ScreeningCalculation


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
