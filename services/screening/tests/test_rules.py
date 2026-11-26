import json
import tempfile
import unittest
from pathlib import Path

from services.screening.rules import RuleConfigError, load_rules


EXAMPLE = Path(__file__).with_name("fixtures") / "example_rules.json"
DRAFT_FLAGS = EXAMPLE.parents[2] / "rule_configs" / "red_flags.draft.json"


class RuleTests(unittest.TestCase):
    def setUp(self):
        self.config = json.loads(EXAMPLE.read_text(encoding="utf-8"))
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.path = Path(directory.name) / "rules.json"

    def write_config(self):
        self.path.write_text(json.dumps(self.config, ensure_ascii=False), encoding="utf-8")
        return self.path

    def expect_invalid(self, field):
        with self.assertRaises(RuleConfigError) as caught:
            load_rules(self.write_config())
        self.assertEqual(caught.exception.version, "v1")
        self.assertEqual(caught.exception.field, field)
        self.assertIn("v1", str(caught.exception))
        self.assertIn(field, str(caught.exception))

    def test_loads_utf8_without_changing_the_json_shape(self):
        rules = load_rules(EXAMPLE)
        self.assertEqual(rules, self.config)
        self.assertEqual(rules["blocks"][1]["questions"][0]["weights"]["yes"], 7)

    def test_rejects_invalid_json_with_line_and_column(self):
        self.path.write_text('{"weights_version": "v1",', encoding="utf-8")
        with self.assertRaisesRegex(RuleConfigError, r"line 1 column \d+"):
            load_rules(self.path)

    def test_detects_duplicate_json_keys_before_json_can_overwrite_them(self):
        source = EXAMPLE.read_text(encoding="utf-8")
        self.path.write_text(source.replace('"yes": 7', '"yes": 7, "yes": 9'), encoding="utf-8")
        with self.assertRaises(RuleConfigError) as caught:
            load_rules(self.path)
        self.assertEqual(caught.exception.version, "v1")
        self.assertEqual(caught.exception.field, "$.blocks[1].questions[0].weights.yes")

    def test_rejects_duplicate_codes(self):
        cases = [
            (("blocks",), "$.blocks[4].code"),
            (("blocks", 0, "questions"), "$.blocks[0].questions[1].code"),
            (("blocks", 0, "questions", 0, "options"), "$.blocks[0].questions[0].options[4].value"),
            (("scoring", "red_flags"), "$.scoring.red_flags[1].code"),
            (("recommendations",), "$.recommendations[4].code"),
        ]
        for keys, field in cases:
            with self.subTest(field=field):
                self.config = load_rules(EXAMPLE)
                items = self.config
                for key in keys:
                    items = items[key]
                items.append(items[0])
                self.expect_invalid(field)

    def test_question_codes_are_unique_across_blocks(self):
        self.config["blocks"][1]["questions"][0]["code"] = "A1"
        self.expect_invalid("$.blocks[1].questions[0].code")

    def test_rejects_unknown_block_question_and_option_references(self):
        for key, field in [
            ("question_code", "$.scoring.red_flags[0].when.question_code"),
            ("option_code", "$.scoring.red_flags[0].when.option_code"),
        ]:
            with self.subTest(field=field):
                self.config = load_rules(EXAMPLE)
                self.config["scoring"]["red_flags"][0]["when"][key] = "unknown"
                self.expect_invalid(field)
        self.config = load_rules(EXAMPLE)
        self.config["scoring"]["sum_blocks"][1] = "B"
        self.expect_invalid("$.scoring.sum_blocks[1]")

    def test_flag_can_reference_a_single_choice_option(self):
        self.config["scoring"]["red_flags"][0]["when"] = {
            "question_code": "A1", "option_code": "four",
        }
        self.assertEqual(load_rules(self.write_config()), self.config)

    def test_rejects_unsupported_scoring_operations(self):
        self.config["scoring"]["red_flags"][0]["when"]["operator"] = "not_equal"
        self.expect_invalid("$.scoring.red_flags[0].when.operator")
        self.config = load_rules(EXAMPLE)
        self.config["scoring"]["red_flags"][0]["priority"] = 1
        self.expect_invalid("$.scoring.red_flags[0].priority")
        self.config = load_rules(EXAMPLE)
        self.config["scoring"]["multiply"] = 2
        self.expect_invalid("$.scoring.multiply")

    def test_requires_boolean_and_choice_weights_for_scored_questions(self):
        del self.config["blocks"][1]["questions"][0]["weights"]["no"]
        self.expect_invalid("$.blocks[1].questions[0].weights.no")
        self.config = load_rules(EXAMPLE)
        del self.config["blocks"][0]["questions"][0]["options"][1]["weight"]
        self.expect_invalid("$.blocks[0].questions[0].options[1].weight")

    def test_requires_explicit_boolean_required_and_integer_weights(self):
        question = self.config["blocks"][0]["questions"][0]
        question["required"] = "true"
        self.expect_invalid("$.blocks[0].questions[0].required")
        question["required"] = True
        question["options"][1]["weight"] = True
        self.expect_invalid("$.blocks[0].questions[0].options[1].weight")

    def test_rejects_overlapping_and_uncovered_score_ranges(self):
        for thresholds, field in [
            ({"low": [1, 4], "medium": [5, 10], "high": [11, None]}, "low"),
            ({"low": [0, 5], "medium": [5, 10], "high": [11, None]}, "medium"),
            ({"low": [0, 4], "medium": [6, 10], "high": [11, None]}, "medium"),
            ({"low": [0, 4], "medium": [5, 10], "high": [11, 18]}, "high"),
            ({"low": [0, None], "medium": [5, 10], "high": [11, None]}, "medium"),
        ]:
            with self.subTest(thresholds=thresholds):
                self.config["scoring"]["thresholds"] = thresholds
                self.expect_invalid(f"$.scoring.thresholds.{field}")

    def test_validate_total_score_fits_screening_v1_int32(self):
        option = self.config["blocks"][0]["questions"][0]["options"][3]
        option["weight"] = 2_147_483_637
        self.assertEqual(load_rules(self.write_config()), self.config)
        option["weight"] += 1
        self.expect_invalid("$.blocks[3].questions[0]")

    def test_accepts_unordered_ranges_and_finite_upper_bound_covering_the_maximum(self):
        self.config["scoring"]["thresholds"] = {
            "high": [11, 19], "low": [0, 4], "medium": [5, 10],
        }
        self.assertEqual(load_rules(self.write_config()), self.config)

    def test_red_flag_level_is_reserved_for_a_flag_match(self):
        scoring = self.config["scoring"]
        scoring["thresholds"]["red_flag"] = scoring["thresholds"].pop("high")
        scoring["outcome_recommendations"]["red_flag"] = scoring["outcome_recommendations"].pop("high")
        self.expect_invalid("$.scoring.thresholds.red_flag")

    def test_requires_recommendations_for_normal_and_urgent_outcomes(self):
        del self.config["scoring"]["outcome_recommendations"]["medium"]
        self.expect_invalid("$.scoring.outcome_recommendations.medium")
        self.config = load_rules(EXAMPLE)
        self.config["scoring"]["red_flags"][0]["recommendation_codes"] = []
        self.expect_invalid("$.scoring.red_flags[0].recommendation_codes")

    def test_rejects_unknown_recommendation_references(self):
        self.config["scoring"]["outcome_recommendations"]["low"] = ["unknown"]
        self.expect_invalid("$.scoring.outcome_recommendations.low[0]")
        self.config = load_rules(EXAMPLE)
        self.config["scoring"]["red_flags"][0]["recommendation_codes"] = ["unknown"]
        self.expect_invalid("$.scoring.red_flags[0].recommendation_codes[0]")

    def test_mis24_draft_flags_form_valid_conditions_with_recommendations(self):
        draft = json.loads(DRAFT_FLAGS.read_text(encoding="utf-8"))
        self.assertEqual(draft["status"], "pending_curator_approval")
        self.config["blocks"][2] = draft["block"]
        self.config["scoring"]["red_flags"] = draft["red_flags"]
        self.config["recommendations"].extend(draft["recommendations"])
        rules = load_rules(self.write_config())
        self.assertEqual(
            {flag["code"] for flag in rules["scoring"]["red_flags"]},
            {
                "rf_pulmonary_hemorrhage",
                "rf_rapidly_progressive_glomerulonephritis",
                "rf_neurological_catastrophe",
                "rf_critical_digital_ischemia",
                "rf_fever_cytopenia",
                "rf_gca_visual_loss",
                "rf_vasculitis_purpura_gi",
            },
        )
        for flag in rules["scoring"]["red_flags"]:
            with self.subTest(flag=flag["code"]):
                self.assertEqual(
                    flag["when"], {"question_code": flag["code"], "option_code": "yes"},
                )
                self.assertEqual(flag["recommendation_codes"], [flag["code"]])
