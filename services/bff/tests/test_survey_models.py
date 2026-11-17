import json
from importlib.resources import files

import pytest
from pydantic import ValidationError

from app.domain.screening import ScreeningSurvey, SubmitAnswerRequest


def survey_payload():
    return json.loads(files("app").joinpath("fixtures/screening_survey.json").read_text())


def test_survey_preserves_supplied_json():
    payload = survey_payload()
    survey = ScreeningSurvey.model_validate(payload)

    assert survey.model_dump(mode="json", exclude_unset=True) == payload
    assert survey.scoring.thresholds.high == (11, None)
    assert survey.blocks[1].questions[0].code == "В1"
    assert survey.blocks[1].questions[0].weights is None


@pytest.mark.parametrize("change", ["unknown_type", "missing_options", "bad_range"])
def test_survey_rejects_invalid_shapes(change):
    payload = survey_payload()
    if change == "unknown_type":
        payload["blocks"][0]["questions"][0]["type"] = "unknown"
    elif change == "missing_options":
        del payload["blocks"][0]["questions"][1]["options"]
    else:
        payload["scoring"]["thresholds"]["high"] = [11]

    with pytest.raises(ValidationError):
        ScreeningSurvey.model_validate(payload)


@pytest.mark.parametrize("value", [True, False, "30-60"])
def test_answer_preserves_boolean_or_choice_value(value):
    answer = SubmitAnswerRequest(question_code="A1", value=value)
    assert answer.value == value
    assert type(answer.value) is type(value)


@pytest.mark.parametrize("value", [1, 0, None, [], {}, ""])
def test_answer_rejects_values_outside_contract(value):
    with pytest.raises(ValidationError):
        SubmitAnswerRequest(question_code="A1", value=value)
