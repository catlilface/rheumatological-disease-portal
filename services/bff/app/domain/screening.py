"""Survey definitions and screening API contracts; no scoring rules are executed here."""

from typing import Annotated, Literal, Self
from uuid import UUID

from pydantic import BaseModel, Field, StrictBool, StringConstraints, model_validator

NonEmptyString = Annotated[str, StringConstraints(strict=True, strip_whitespace=True, min_length=1)]


class BooleanWeights(BaseModel):
    yes: float
    no: float


class Question(BaseModel):
    code: NonEmptyString
    text: NonEmptyString
    required: bool
    red_flag: bool = False


class BooleanQuestion(Question):
    type: Literal["boolean"]
    weights: BooleanWeights | None = None


class ChoiceOption(BaseModel):
    value: NonEmptyString
    label: NonEmptyString
    weight: float


class SingleChoiceQuestion(Question):
    type: Literal["single_choice"]
    options: list[ChoiceOption] = Field(min_length=1)


SurveyQuestion = Annotated[BooleanQuestion | SingleChoiceQuestion, Field(discriminator="type")]


class SurveyBlock(BaseModel):
    code: NonEmptyString
    red_flag: bool = False
    interrupt: bool = False
    questions: list[SurveyQuestion] = Field(min_length=1)


class ScoreThresholds(BaseModel):
    low: tuple[float, float | None]
    medium: tuple[float, float | None]
    high: tuple[float, float | None]


class ScoringConfig(BaseModel):
    sum_blocks: list[NonEmptyString]
    thresholds: ScoreThresholds
    red_flag_overrides: bool


class ScreeningSurvey(BaseModel):
    id: NonEmptyString
    weights_version: NonEmptyString
    blocks: list[SurveyBlock] = Field(min_length=1)
    scoring: ScoringConfig


ScreeningStatus = Literal["in_progress", "completed", "interrupted"]


class StartScreeningRequest(BaseModel):
    survey_id: NonEmptyString


class ScreeningSession(BaseModel):
    id: UUID
    status: ScreeningStatus
    survey: ScreeningSurvey


class SubmitAnswerRequest(BaseModel):
    question_code: NonEmptyString
    value: StrictBool | NonEmptyString


class AnswerReceipt(BaseModel):
    screening_id: UUID
    answer: SubmitAnswerRequest
    status: ScreeningStatus


class ScreeningResult(BaseModel):
    screening_id: UUID
    survey_id: NonEmptyString
    weights_version: NonEmptyString
    status: ScreeningStatus
    score: float | None = None
    risk_level: Literal["low", "medium", "high", "red_flag"]
    red_flag: bool
    disclaimer: str

    @model_validator(mode="after")
    def validate_result(self) -> Self:
        if self.red_flag != (self.risk_level == "red_flag"):
            raise ValueError("red_flag must agree with risk_level")
        if self.score is None and not self.red_flag:
            raise ValueError("a score is required for a non-red-flag result")
        return self
