"""Load and register immutable versions of Screening's JSON rules."""

import json
from copy import deepcopy
from pathlib import Path
from threading import Lock


class RuleConfigError(ValueError):
    """A configuration error at a specific field of a rules version."""

    def __init__(self, version, field, message):
        self.version = version
        self.field = field
        super().__init__(f"Rules version {version!r}, {field}: {message}")


class _ObjectPairs(list):
    """Keep duplicate JSON object keys visible until their path is known."""


def _decode(value, field, version):
    if isinstance(value, _ObjectPairs):
        result = {}
        for key, item in value:
            key_field = f"{field}.{key}"
            if key in result:
                raise RuleConfigError(version, key_field, "duplicate JSON key")
            result[key] = _decode(item, key_field, version)
        return result
    if isinstance(value, list):
        return [_decode(item, f"{field}[{index}]", version) for index, item in enumerate(value)]
    return value


def _invalid_json_constant(value):
    raise ValueError(f"{value} is not a JSON value")


def load_rules(path: str | Path) -> dict:
    """Read a UTF-8 JSON file and return its validated definition."""
    path = Path(path)
    unknown_version = "<unknown>"
    try:
        raw = json.loads(
            path.read_text(encoding="utf-8"),
            object_pairs_hook=_ObjectPairs,
            parse_constant=_invalid_json_constant,
        )
    except json.JSONDecodeError as exc:
        raise RuleConfigError(
            unknown_version, "$", f"invalid JSON in {path}: {exc}",
        ) from exc
    except (OSError, ValueError) as exc:
        raise RuleConfigError(unknown_version, "$", f"cannot read {path}: {exc}") from exc

    version = next(
        (value for key, value in raw if key == "weights_version" and isinstance(value, str)),
        unknown_version,
    ) if isinstance(raw, _ObjectPairs) else unknown_version
    data = _decode(raw, "$", version)
    return validate_rules(data)


def validate_rules(data: dict) -> dict:
    """Validate the decoded definition, including definitions read from JSONB."""
    version = data.get("weights_version", "<unknown>") if isinstance(data, dict) else "<unknown>"
    values = _ValueValidator(version if isinstance(version, str) else "<unknown>")
    values.object(data, "$")
    values.text(data.get("id"), "$.id")
    values.text(data.get("weights_version"), "$.weights_version")
    scoring = values.object(data.get("scoring"), "$.scoring")
    values.check_fields(scoring, "$.scoring", {
        "sum_blocks", "thresholds", "outcome_recommendations", "red_flags",
    })
    sum_blocks = dict(values.codes(scoring.get("sum_blocks"), "$.scoring.sum_blocks"))
    questions, maximum = _BlockValidator(values).validate(data.get("blocks"), sum_blocks)
    levels = _ThresholdValidator(values).validate(scoring.get("thresholds"), maximum)
    recommendation_validator = _RecommendationValidator(values)
    recommendations = recommendation_validator.validate(data.get("recommendations"))
    recommendation_validator.outcomes(scoring.get("outcome_recommendations"), levels, recommendations)
    _RedFlagValidator(values, recommendation_validator).validate(
        scoring.get("red_flags"), questions, recommendations,
    )
    return data


class _ValueValidator:
    """Check JSON value types and uniqueness, preserving versioned field errors."""

    def __init__(self, version):
        self.version = version

    def fail(self, field, message):
        raise RuleConfigError(self.version, field, message)

    def object(self, value, field):
        if not isinstance(value, dict):
            self.fail(field, "expected an object")
        return value

    def array(self, value, field, *, nonempty=False):
        if not isinstance(value, list) or (nonempty and not value):
            self.fail(field, "expected a non-empty array" if nonempty else "expected an array")
        return value

    def text(self, value, field):
        if not isinstance(value, str) or not value.strip():
            self.fail(field, "expected a non-empty string")
        return value

    def points(self, value, field):
        if type(value) is not int or value < 0:
            self.fail(field, "expected a non-negative integer")
        return value

    def unique(self, code, seen, field):
        if code in seen:
            self.fail(field, f"duplicate code {code!r}")
        seen.add(code)

    def objects(self, value, field, *, nonempty=False):
        for index, item in enumerate(self.array(value, field, nonempty=nonempty)):
            item_field = f"{field}[{index}]"
            yield self.object(item, item_field), item_field

    def check_fields(self, value, field, allowed):
        for key in value:
            if key not in allowed:
                self.fail(f"{field}.{key}", "unsupported field")

    def codes(self, value, field):
        seen = set()
        for index, item in enumerate(self.array(value, field, nonempty=True)):
            item_field = f"{field}[{index}]"
            code = self.text(item, item_field)
            self.unique(code, seen, item_field)
            yield code, item_field


class _QuestionValidator:
    """Validate answer options and weights for a single question."""

    def __init__(self, values):
        self.values = values

    def validate(self, question, field, scored):
        self.values.text(question.get("text"), f"{field}.text")
        if type(question.get("required")) is not bool:
            self.values.fail(f"{field}.required", "expected a boolean")
        kind = question.get("type")
        if kind == "boolean":
            options = {"yes", "no"}
            weights = []
            if scored or "weights" in question:
                weights_field = f"{field}.weights"
                weights_by_option = self.values.object(question.get("weights"), weights_field)
                for code in ("yes", "no"):
                    weights.append(self.values.points(weights_by_option.get(code), f"{weights_field}.{code}"))
                for code in weights_by_option.keys() - options:
                    self.values.fail(f"{weights_field}.{code}", "unknown boolean option")
            return options, max(weights, default=0)
        if kind != "single_choice":
            self.values.fail(f"{field}.type", "expected boolean or single_choice")
        options = set()
        weights = []
        for option, option_field in self.values.objects(
            question.get("options"), f"{field}.options", nonempty=True,
        ):
            code = self.values.text(option.get("value"), f"{option_field}.value")
            self.values.unique(code, options, f"{option_field}.value")
            self.values.text(option.get("label"), f"{option_field}.label")
            if scored or "weight" in option:
                weights.append(self.values.points(option.get("weight"), f"{option_field}.weight"))
        return options, max(weights, default=0)


class _BlockValidator:
    """Index questions, resolve sum blocks and bound the attainable score."""

    def __init__(self, values):
        self.values = values
        self.question_validator = _QuestionValidator(values)

    def validate(self, value, sum_blocks):
        seen_blocks = set()
        questions = {}
        maximum = 0
        for block, field in self.values.objects(value, "$.blocks", nonempty=True):
            code = self.values.text(block.get("code"), f"{field}.code")
            self.values.unique(code, seen_blocks, f"{field}.code")
            scored = code in sum_blocks
            for question, question_field in self.values.objects(
                block.get("questions"), f"{field}.questions", nonempty=True,
            ):
                question_code = self.values.text(question.get("code"), f"{question_field}.code")
                if question_code in questions:
                    self.values.fail(f"{question_field}.code", f"duplicate code {question_code!r}")
                options, points = self.question_validator.validate(question, question_field, scored)
                questions[question_code] = options
                if scored:
                    maximum += points
                    if maximum > 2_147_483_647:
                        self.values.fail(question_field, "maximum total score exceeds the Screening v1 int32 limit")
        for code, field in sum_blocks.items():
            if code not in seen_blocks:
                self.values.fail(field, f"unknown block {code!r}")
        return questions, maximum


class _ThresholdValidator:
    """Check that outcome ranges cover attainable scores without gaps or overlaps."""

    def __init__(self, values):
        self.values = values

    def validate(self, value, maximum):
        root = "$.scoring.thresholds"
        thresholds = self.values.object(value, root)
        if not thresholds:
            self.values.fail(root, "expected at least one score range")
        ranges = []
        for level, bounds in thresholds.items():
            field = f"{root}.{level}"
            self.values.text(level, field)
            if level == "red_flag":
                self.values.fail(field, "reserved for a red flag outcome")
            bounds = self.values.array(bounds, field)
            if len(bounds) != 2:
                self.values.fail(field, "expected [minimum, maximum]")
            lower = self.values.points(bounds[0], f"{field}[0]")
            upper = self.values.points(bounds[1], f"{field}[1]") if bounds[1] is not None else None
            if upper is not None and upper < lower:
                self.values.fail(field, "maximum is below minimum")
            ranges.append((lower, upper, field))

        next_score = 0
        for lower, upper, field in sorted(ranges, key=lambda bounds: bounds[0]):
            if next_score is None or lower < next_score:
                self.values.fail(field, "score ranges overlap")
            if lower > next_score:
                self.values.fail(field, f"score {next_score} is not covered")
            next_score = None if upper is None else upper + 1
        if next_score is not None and next_score <= maximum:
            self.values.fail(field, f"range must cover the maximum attainable score {maximum}")
        return thresholds.keys()


class _RecommendationValidator:
    """Validate the recommendation catalog and references from outcomes or flags."""

    def __init__(self, values):
        self.values = values

    def validate(self, value):
        codes = set()
        for recommendation, field in self.values.objects(value, "$.recommendations", nonempty=True):
            code = self.values.text(recommendation.get("code"), f"{field}.code")
            self.values.unique(code, codes, f"{field}.code")
            self.values.text(recommendation.get("text"), f"{field}.text")
        return codes

    def references(self, value, recommendations, field):
        for code, code_field in self.values.codes(value, field):
            if code not in recommendations:
                self.values.fail(code_field, f"unknown recommendation {code!r}")

    def outcomes(self, value, levels, recommendations):
        field = "$.scoring.outcome_recommendations"
        outcomes = self.values.object(value, field)
        for level in levels:
            self.references(outcomes.get(level), recommendations, f"{field}.{level}")
        for level in outcomes.keys() - levels:
            self.values.fail(f"{field}.{level}", "unknown outcome")


class _RedFlagValidator:
    """Resolve red flag conditions against validated questions and recommendations."""

    def __init__(self, values, recommendation_validator):
        self.values = values
        self.recommendation_validator = recommendation_validator

    def validate(self, value, questions, recommendations):
        seen = set()
        for flag, field in self.values.objects(value, "$.scoring.red_flags"):
            self.values.check_fields(flag, field, {"code", "when", "recommendation_codes"})
            code = self.values.text(flag.get("code"), f"{field}.code")
            self.values.unique(code, seen, f"{field}.code")
            condition = self.values.object(flag.get("when"), f"{field}.when")
            self.values.check_fields(condition, f"{field}.when", {"question_code", "option_code"})
            question_field = f"{field}.when.question_code"
            option_field = f"{field}.when.option_code"
            question = self.values.text(condition.get("question_code"), question_field)
            if question not in questions:
                self.values.fail(question_field, f"unknown question {question!r}")
            option = self.values.text(condition.get("option_code"), option_field)
            if option not in questions[question]:
                self.values.fail(option_field, f"unknown option {option!r} for question {question!r}")
            self.recommendation_validator.references(
                flag.get("recommendation_codes"), recommendations, f"{field}.recommendation_codes",
            )


class RuleRegistry:
    """A local registry with exact-version lookup and explicit publication."""

    def __init__(self):
        self._versions = {}
        self._current = {}
        self._lock = Lock()

    def publish(self, path: str | Path) -> None:
        """Validate first, then make a new version current for its scale."""
        rules = load_rules(path)
        scale, version = rules["id"], rules["weights_version"]
        with self._lock:
            key = (scale, version)
            if key in self._versions:
                if json.dumps(self._versions[key], sort_keys=True) != json.dumps(rules, sort_keys=True):
                    raise RuleConfigError(
                        version, "$.weights_version", f"rules for {scale!r} require a new version",
                    )
                return
            self._versions[key] = rules
            self._current[scale] = version

    def get(self, scale: str, version: str | None = None) -> dict:
        """Return a copy of the requested version, or the current one if omitted."""
        with self._lock:
            selected = self._current[scale] if version is None else version
            return deepcopy(self._versions[scale, selected])
