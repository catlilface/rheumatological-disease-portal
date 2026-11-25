"""Answer contributions and the explained result of a screening calculation."""

from dataclasses import dataclass
from typing import Literal


AnswerValue = bool | str
ScoreRange = tuple[int, int | None]


@dataclass(frozen=True, slots=True)
class ScoredAnswer:
    question_code: str
    block_code: str
    value: AnswerValue
    weighted_score: int


@dataclass(frozen=True, slots=True)
class RedFlagMatch:
    code: str
    question_code: str
    option_code: str
    matched_current_answer: bool


@dataclass(frozen=True, slots=True)
class Recommendation:
    code: str
    text: str


@dataclass(frozen=True, slots=True)
class ScreeningCalculation:
    survey_id: str
    weights_version: str
    block_scores: dict[str, int]
    total_score: int | None
    scoring_complete: bool
    level: str | None
    reason: Literal["score", "red_flag", "incomplete"]
    matched_range: ScoreRange | None
    missing_required: tuple[str, ...]
    contributing_answers: tuple[ScoredAnswer, ...]
    red_flags: tuple[RedFlagMatch, ...]
    recommendations: tuple[Recommendation, ...]
