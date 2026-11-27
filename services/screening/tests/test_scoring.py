import json
import tempfile
import unittest
from pathlib import Path

from services.screening.registry import LocalRegistry
from services.screening.rules import load_rules
from services.screening.scoring import AnswerError, calculate_result


EXAMPLE = Path(__file__).with_name("fixtures") / "example_rules.json"
DRAFT_FLAGS = EXAMPLE.parents[2] / "rule_configs" / "red_flags.draft.json"
NORMAL_RECOMMENDATIONS = {
    "low": "Тестовое сообщение для низкого уровня.",
    "medium": "Тестовое сообщение для среднего уровня.",
    "high": "Тестовое сообщение для высокого уровня.",
}


class ScoringTests(unittest.TestCase):
    def setUp(self):
        self.rules = load_rules(EXAMPLE)

    def validated(self, rules):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "rules.json"
            path.write_text(json.dumps(rules, ensure_ascii=False), encoding="utf-8")
            return load_rules(path)

    def test_mis24_synthetic_boundary_profiles(self):
        cases = [
            ("zero", False, False, (0, 0, 0), 0, "low", (0, 4)),
            ("four", False, False, (4, 0, 0), 4, "low", (0, 4)),
            ("five", False, False, (5, 0, 0), 5, "medium", (5, 10)),
            ("zero", True, True, (0, 7, 3), 10, "medium", (5, 10)),
            ("four", True, False, (4, 7, 0), 11, "high", (11, None)),
            ("nine", True, True, (9, 7, 3), 19, "high", (11, None)),
        ]
        for choice, b, g, scores, total, level, bounds in cases:
            with self.subTest(total=total):
                answers = {"Г1": g, "В1": False, "Б1": b, "A1": choice}
                result = calculate_result(self.rules, answers)
                self.assertEqual((result.survey_id, result.weights_version), ("example", "v1"))
                self.assertEqual(result.block_scores, dict(zip(("A", "Б", "Г"), scores)))
                self.assertEqual(result.total_score, total)
                self.assertEqual(result.level, level)
                self.assertEqual(result.reason, "score")
                self.assertEqual(result.matched_range, bounds)
                self.assertTrue(result.scoring_complete)
                self.assertEqual(result.missing_required, ())
                self.assertEqual(result.red_flags, ())
                self.assertEqual(
                    [(r.code, r.text) for r in result.recommendations],
                    [(level, NORMAL_RECOMMENDATIONS[level])],
                )
                self.assertEqual(
                    [(a.question_code, a.block_code, a.value, a.weighted_score)
                     for a in result.contributing_answers],
                    [("A1", "A", choice, scores[0]), ("Б1", "Б", b, scores[1]), ("Г1", "Г", g, scores[2])],
                )

    def test_omitted_optional_answer_contributes_zero_without_creating_an_answer(self):
        result = calculate_result(self.rules, {"A1": "four", "В1": False, "Г1": False})
        self.assertTrue(result.scoring_complete)
        self.assertEqual(result.total_score, 4)
        self.assertEqual(result.block_scores["Б"], 0)
        self.assertEqual([a.question_code for a in result.contributing_answers], ["A1", "Г1"])

    def test_incomplete_without_red_flag_has_no_level_or_total(self):
        result = calculate_result(self.rules, {"В1": False, "Б1": True})
        self.assertEqual(result.reason, "incomplete")
        self.assertIsNone(result.level)
        self.assertIsNone(result.matched_range)
        self.assertIsNone(result.total_score)
        self.assertFalse(result.scoring_complete)
        self.assertEqual(result.missing_required, ("A1", "Г1"))
        self.assertEqual(result.block_scores, {"A": 0, "Б": 7, "Г": 0})
        self.assertEqual(result.recommendations, ())

    def test_missing_required_flag_question_prevents_a_numeric_result(self):
        result = calculate_result(self.rules, {"A1": "nine", "Б1": True, "Г1": True})
        self.assertEqual(result.missing_required, ("В1",))
        self.assertEqual(result.reason, "incomplete")
        self.assertIsNone(result.level)
        self.assertIsNone(result.total_score)

    def test_each_mis24_draft_flag_produces_urgent_result_at_zero_and_when_incomplete(self):
        draft = json.loads(DRAFT_FLAGS.read_text(encoding="utf-8"))
        self.rules["blocks"][2] = draft["block"]
        self.rules["scoring"]["red_flags"] = draft["red_flags"]
        self.rules["recommendations"].extend(draft["recommendations"])
        rules = self.validated(self.rules)
        recommendation_text = {r["code"]: r["text"] for r in draft["recommendations"]}
        for flag in draft["red_flags"]:
            code = flag["code"]
            for complete in (False, True):
                with self.subTest(flag=code, complete=complete):
                    answers = {code: True}
                    if complete:
                        answers.update({"A1": "zero", "Б1": False, "Г1": False})
                    result = calculate_result(rules, answers)
                    self.assertEqual((result.level, result.reason), ("red_flag", "red_flag"))
                    self.assertEqual(result.scoring_complete, complete)
                    self.assertEqual(result.total_score, 0 if complete else None)
                    self.assertIsNone(result.matched_range)
                    self.assertEqual(
                        [(f.code, f.question_code, f.option_code, f.matched_current_answer)
                         for f in result.red_flags],
                        [(code, code, "yes", True)],
                    )
                    self.assertEqual(
                        [(r.code, r.text) for r in result.recommendations],
                        [(code, recommendation_text[code])],
                    )

    def test_multiple_flags_explain_all_triggers_and_deduplicate_recommendations(self):
        self.rules["scoring"]["red_flags"].append({
            "code": "choice_flag",
            "when": {"question_code": "A1", "option_code": "nine"},
            "recommendation_codes": ["urgent", "high"],
        })
        rules = self.validated(self.rules)
        answers = {"A1": "nine", "Б1": True, "В1": True, "Г1": True}
        result = calculate_result(rules, answers)
        self.assertEqual(result.level, "red_flag")
        self.assertEqual(result.total_score, 19)
        self.assertIsNone(result.matched_range)
        self.assertEqual([f.code for f in result.red_flags], ["example_flag", "choice_flag"])
        self.assertEqual([f.option_code for f in result.red_flags], ["yes", "nine"])
        self.assertEqual([r.code for r in result.recommendations], ["urgent", "high"])
        self.assertEqual(result, calculate_result(rules, dict(reversed(list(answers.items())))))

    def test_previously_detected_flag_is_explained_even_after_changing_trigger_answer(self):
        result = calculate_result(
            self.rules, {"A1": "nine", "Б1": True, "В1": False, "Г1": True},
            previous_red_flag_codes=("example_flag",),
        )
        self.assertEqual((result.level, result.total_score), ("red_flag", 19))
        self.assertEqual(len(result.red_flags), 1)
        flag = result.red_flags[0]
        self.assertEqual((flag.code, flag.question_code, flag.option_code), ("example_flag", "В1", "yes"))
        self.assertFalse(flag.matched_current_answer)
        self.assertEqual([r.code for r in result.recommendations], ["urgent"])

    def test_rejects_flag_history_inconsistent_with_the_pinned_version(self):
        with self.assertRaisesRegex(ValueError, "unknown previous red flag"):
            calculate_result(self.rules, {}, previous_red_flag_codes=("unknown_flag",))

    def test_rejects_a_string_in_place_of_flag_history(self):
        with self.assertRaisesRegex(TypeError, "collection of flag codes"):
            calculate_result(self.rules, {}, previous_red_flag_codes="example_flag")

    def test_rejects_unknown_answers_and_wrong_value_types(self):
        for code, value in (
            ("A99", True), ("A1", False), ("A1", "not_a_choice"),
            ("Б1", 1), ("Г1", None), ("В1", "yes"), ("B1", False),
        ):
            with self.subTest(question=code, value=value):
                with self.assertRaises(AnswerError) as caught:
                    calculate_result(self.rules, {code: value, "В1": True} if code != "В1" else {code: value})
                self.assertEqual(caught.exception.question_code, code)

    def test_scores_two_versions_of_the_same_answers_using_the_pinned_definition(self):
        registry = LocalRegistry()
        registry.publish(EXAMPLE)
        self.rules["weights_version"] = "v2"
        self.rules["blocks"][1]["questions"][0]["weights"]["yes"] = 6
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "v2.json"
            path.write_text(json.dumps(self.rules), encoding="utf-8")
            registry.publish(path)
        answers = {"A1": "four", "Б1": True, "В1": False, "Г1": False}
        original = calculate_result(registry.get("example", "v1"), answers)
        updated = calculate_result(registry.get("example", "v2"), answers)
        self.assertEqual((original.weights_version, original.total_score, original.level), ("v1", 11, "high"))
        self.assertEqual((updated.weights_version, updated.total_score, updated.level), ("v2", 10, "medium"))

    def test_another_scale_controls_blocks_weights_thresholds_and_recommendations(self):
        second = self.validated({
            "id": "other",
            "weights_version": "v3",
            "blocks": [{"code": "Z", "questions": [{
                "code": "Z1", "text": "Вопрос другой шкалы", "type": "boolean",
                "required": True, "weights": {"yes": 0, "no": 2},
            }]}],
            "scoring": {
                "sum_blocks": ["Z"],
                "thresholds": {"clear": [0, 0], "review": [1, 2]},
                "outcome_recommendations": {"clear": ["r0"], "review": ["r1", "r0"]},
                "red_flags": [],
            },
            "recommendations": [{"code": "r0", "text": "Один"}, {"code": "r1", "text": "Два"}],
        })
        result = calculate_result(second, {"Z1": False})
        self.assertEqual((result.survey_id, result.weights_version), ("other", "v3"))
        self.assertEqual(result.block_scores, {"Z": 2})
        self.assertEqual(result.total_score, 2)
        self.assertEqual(result.level, "review")
        self.assertEqual(result.matched_range, (1, 2))
        self.assertEqual([(r.code, r.text) for r in result.recommendations], [("r1", "Два"), ("r0", "Один")])
