"""Keep the 0.1.10 entity identity contract while adding native controls."""

import ast
import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
INTEGRATION = ROOT / "custom_components/thermia_calibra"


class CompatibilityTests(unittest.TestCase):
    def test_legacy_entity_keys_and_unique_id_expressions_are_preserved(self):
        fixture = json.loads((ROOT / "tests/fixtures/legacy_entities.json").read_text())
        total = 0
        for platform, baseline in fixture.items():
            tree = ast.parse((INTEGRATION / f"{platform}.py").read_text())
            keys = {
                node.value.value for node in ast.walk(tree)
                if isinstance(node, ast.keyword) and node.arg == "key"
                and isinstance(node.value, ast.Constant)
            }
            if platform != "select":
                self.assertTrue(set(baseline["keys"]) <= keys, platform)
            expressions = [
                node.value for node in ast.walk(tree)
                if isinstance(node, ast.Assign)
                and any(isinstance(target, ast.Attribute) and target.attr == "_attr_unique_id" for target in node.targets)
            ]
            self.assertEqual(len(expressions), len(baseline["unique_id"]), platform)
            for actual, expected in zip(expressions, baseline["unique_id"]):
                self.assertEqual(ast.dump(actual), ast.dump(ast.parse(expected, mode="eval").body), platform)
            total += len(baseline["keys"])
        self.assertEqual(total, 48)

    def test_display_rename_does_not_change_device_identity_or_domain(self):
        tree = ast.parse((INTEGRATION / "const.py").read_text())
        constants = {
            node.targets[0].id: node.value.value
            for node in tree.body if isinstance(node, ast.Assign)
            and isinstance(node.targets[0], ast.Name) and isinstance(node.value, ast.Constant)
        }
        self.assertEqual(constants["DOMAIN"], "thermia_calibra")
        self.assertEqual(constants["DEVICE_NAME"], "Thermia Calibra Cool 7 BW")
        self.assertEqual(constants["DEVICE_MODEL"], "Calibra Cool 7 BW / Genesis")
        self.assertEqual(constants["INTEGRATION_NAME"], "Thermia Calibra Modbus")

    def test_manifests_and_translations_are_consistent(self):
        manifest = json.loads((INTEGRATION / "manifest.json").read_text())
        hacs = json.loads((ROOT / "hacs.json").read_text())
        self.assertEqual(manifest["domain"], "thermia_calibra")
        self.assertEqual(manifest["name"], hacs["name"])
        translations = [json.loads((INTEGRATION / path).read_text()) for path in ("strings.json", "translations/en.json", "translations/nl.json")]
        self.assertEqual(translations[0], translations[1])
        for translation in translations:
            self.assertEqual(translation["config"]["step"]["user"]["title"], manifest["name"])
            self.assertEqual(len(translation["entity"]["number"]), 15)
            self.assertEqual(set(translation["entity"]["number"]), set(translations[0]["entity"]["number"]))


if __name__ == "__main__":
    unittest.main()
