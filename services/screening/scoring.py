"""Calculate a Screening result from validated rules and saved answers."""

from collections.abc import Collection, Mapping
from dataclasses import dataclass
from typing import Literal


AnswerValue = bool | str
ScoreRange = tuple[int, int | None]


class AnswerError(ValueError):
    """A saved answer does not match the session's version of the scale."""

    def __init__(self, question_code: str, message: str):
        self.question_code = question_code
        super().__init__(f"Question {question_code!r}: {message}")


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


def _option_code_and_weight(question: Mapping, value: AnswerValue) -> tuple[str, int]:
    if question["type"] == "boolean":
        if type(value) is not bool:
            raise AnswerError(question["code"], "expected a boolean")
        option_code = "yes" if value else "no"
        return option_code, question.get("weights", {}).get(option_code, 0)

    if not isinstance(value, str):
        raise AnswerError(question["code"], "expected a choice code")
    for option in question["options"]:
        if option["value"] == value:
            return value, option.get("weight", 0)
    raise AnswerError(question["code"], "unknown choice code")


def _match_flags(
    flags: list[dict],
    answers: Mapping[str, str],
    previous_codes: Collection[str],
) -> tuple[list[RedFlagMatch], list[str]]:
    if isinstance(previous_codes, str):
        raise TypeError("previous_red_flag_codes must be a collection of flag codes")
    remaining = set(previous_codes)
    matches = []
    recommendations = []
    for flag in flags:
        code = flag["code"]
        question = flag["when"]["question_code"]
        option = flag["when"]["option_code"]
        matched = answers.get(question) == option
        if matched or code in remaining:
            matches.append(RedFlagMatch(code, question, option, matched))
            recommendations.extend(flag["recommendation_codes"])
        remaining.discard(code)
    if remaining:
        raise ValueError(f"unknown previous red flag {min(remaining)!r} for these rules")
    return matches, recommendations


def _score_level(thresholds: Mapping[str, list], score: int) -> tuple[str, ScoreRange]:
    for level, (lower, upper) in thresholds.items():
        if lower <= score and (upper is None or score <= upper):
            return level, (lower, upper)
    raise ValueError(f"score {score} is outside the configured ranges")


def calculate_result(
    rules: Mapping,
    answers: Mapping[str, AnswerValue],
    *,
    previous_red_flag_codes: Collection[str] = (),
) -> ScreeningCalculation:
    """Apply the session's validated rules to its saved answer values.

    Previously detected flags may be supplied by the caller from the same
    session and rules version so that continuing a screening preserves them.
    """
    questions = {
        question["code"]: (block["code"], question)
        for block in rules["blocks"]
        for question in block["questions"]
    }
    for code in answers:
        if code not in questions:
            raise AnswerError(code, "unknown question code")

    scoring = rules["scoring"]
    block_scores = dict.fromkeys(scoring["sum_blocks"], 0)
    answer_codes = {}
    missing_required = []
    contributions = []
    for code, (block_code, question) in questions.items():
        if code not in answers:
            if question["required"]:
                missing_required.append(code)
            continue

        value = answers[code]
        option, weight = _option_code_and_weight(question, value)
        answer_codes[code] = option
        if block_code in block_scores:
            block_scores[block_code] += weight
            contributions.append(ScoredAnswer(code, block_code, value, weight))

    flags, recommendation_codes = _match_flags(
        scoring["red_flags"], answer_codes, previous_red_flag_codes,
    )
    total_score = None if missing_required else sum(block_scores.values())
    matched_range = None
    if flags:
        level, reason = "red_flag", "red_flag"
    elif total_score is None:
        level, reason = None, "incomplete"
    else:
        level, matched_range = _score_level(scoring["thresholds"], total_score)
        reason = "score"
        recommendation_codes = scoring["outcome_recommendations"][level]

    recommendation_texts = {item["code"]: item["text"] for item in rules["recommendations"]}
    return ScreeningCalculation(
        survey_id=rules["id"],
        weights_version=rules["weights_version"],
        block_scores=block_scores,
        total_score=total_score,
        scoring_complete=not missing_required,
        level=level,
        reason=reason,
        matched_range=matched_range,
        missing_required=tuple(missing_required),
        contributing_answers=tuple(contributions),
        red_flags=tuple(flags),
        recommendations=tuple(
            Recommendation(code, recommendation_texts[code]) for code in dict.fromkeys(recommendation_codes)
        ),
    )
