import json
import tempfile
import unittest
from pathlib import Path

from services.screening.registry import BaseRegistry, LocalRegistry
from services.screening.rules import RuleConfigError, load_rules


EXAMPLE = Path(__file__).with_name("fixtures") / "example_rules.json"


class LocalRegistryTests(unittest.TestCase):
    def setUp(self):
        self.registry: BaseRegistry = LocalRegistry()
        self.config = load_rules(EXAMPLE)
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.path = Path(directory.name) / "rules.json"

    def write_config(self):
        self.path.write_text(json.dumps(self.config, ensure_ascii=False), encoding="utf-8")
        return self.path

    def test_invalid_publication_does_not_replace_the_current_version(self):
        registry = self.registry
        registry.publish(EXAMPLE)
        self.config["weights_version"] = "v2"
        del self.config["scoring"]["outcome_recommendations"]["low"]
        with self.assertRaises(RuleConfigError) as caught:
            registry.publish(self.write_config())
        self.assertEqual(caught.exception.version, "v2")
        self.assertEqual(registry.get("example")["weights_version"], "v1")
        with self.assertRaises(KeyError):
            registry.get("example", "v2")

    def test_keeps_exact_versions_and_loads_another_scale(self):
        registry = self.registry
        registry.publish(EXAMPLE)
        self.config["weights_version"] = "v2"
        self.config["blocks"][1]["questions"][0]["weights"]["yes"] = 6
        registry.publish(self.write_config())
        self.config["id"] = "second"
        registry.publish(self.write_config())
        self.assertEqual(registry.get("example")["weights_version"], "v2")
        self.assertEqual(registry.get("example", "v1")["blocks"][1]["questions"][0]["weights"]["yes"], 7)
        self.assertEqual(registry.get("second")["id"], "second")

    def test_same_version_cannot_be_modified_and_returned_data_cannot_mutate_it(self):
        registry = self.registry
        registry.publish(EXAMPLE)
        returned = registry.get("example", "v1")
        returned["blocks"][0]["questions"][0]["options"][0]["weight"] = 1
        self.assertEqual(registry.get("example", "v1"), self.config)
        self.config["blocks"][0]["questions"][0]["options"][0]["weight"] = 1
        with self.assertRaises(RuleConfigError) as caught:
            registry.publish(self.write_config())
        self.assertEqual(caught.exception.field, "$.weights_version")
        self.assertEqual(registry.get("example", "v1")["blocks"][0]["questions"][0]["options"][0]["weight"], 0)

    def test_republishing_identical_old_version_does_not_make_it_current(self):
        registry = self.registry
        registry.publish(EXAMPLE)
        self.config["weights_version"] = "v2"
        registry.publish(self.write_config())
        self.config["weights_version"] = "v1"
        self.path.write_text(json.dumps(self.config, sort_keys=True), encoding="utf-8")
        registry.publish(self.path)
        self.assertEqual(registry.get("example")["weights_version"], "v2")

    def test_rejects_changes_in_json_types_within_a_published_version(self):
        registry = self.registry
        self.config["blocks"][2]["interrupt"] = True
        registry.publish(self.write_config())
        self.config["blocks"][2]["interrupt"] = 1
        with self.assertRaises(RuleConfigError) as caught:
            registry.publish(self.write_config())
        self.assertEqual(caught.exception.field, "$.weights_version")
        self.assertIs(registry.get("example", "v1")["blocks"][2]["interrupt"], True)
