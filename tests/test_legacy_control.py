"""The simplified device integration must not abandon old temporary writes."""

import ast
from copy import deepcopy
import importlib.util
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
INTEGRATION = ROOT / "custom_components/thermia_calibra"
spec = importlib.util.spec_from_file_location("legacy_control", INTEGRATION / "legacy_control.py")
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def restored_journal():
    return {
        "ownership": {}, "blocked": None,
        "control": {
            "overrides": {}, "pending_restore": [],
            "charge_active": {"heating": False, "hot_water": False},
            "heating_preset": "normal", "hot_water_mode": "auto",
            "heating_excess_deadline": None, "hot_water_excess_deadline": None,
            "hot_water_low_deadline": None,
        },
    }


class LegacyUpgradeTests(unittest.TestCase):
    def test_fresh_install_or_controller_never_used(self):
        for saved in (None, {}):
            self.assertIsNone(module.legacy_control_problem({}, saved))
            self.assertIsNone(module.legacy_control_problem({"controller_enabled": False}, saved))

    def test_enabled_or_malformed_enable_option_blocks_upgrade(self):
        for enabled in (True, None, "false", 0):
            self.assertIsNotNone(module.legacy_control_problem({"controller_enabled": enabled}, None))

    def test_disabled_and_restored_controller_is_allowed(self):
        journal = restored_journal()
        journal["control"]["managed_heating"] = True
        journal["control"]["heating_mode"] = "heat"
        self.assertIsNone(module.legacy_control_problem({"controller_enabled": False}, journal))

    def test_unknown_or_incomplete_journal_blocks_upgrade(self):
        for saved in ([], "invalid", {"ownership": {}}, {"control": {}}, {"ownership": {}, "control": {}}):
            self.assertIsNotNone(module.legacy_control_problem({}, saved))

    def test_owned_or_suspended_values_block_even_with_controller_off(self):
        for key, value in (("blocked", "external change"), ("ownership", {"comfort_wheel": {"after": 25}})):
            journal = restored_journal()
            journal[key] = value
            self.assertIsNotNone(module.legacy_control_problem({"controller_enabled": False}, journal))

    def test_pending_overrides_and_recovery_block_upgrade(self):
        for key, value in (
            ("overrides", {"heating": {"comfort_wheel": 23}}),
            ("pending_restore", ["hot_water"]),
            ("charge_active", {"heating": True}),
            ("sg_owners", ["heating"]),
            ("boost_once", True), ("boost_enabled", True),
            ("native_boost_coupled", True), ("cooling_humidity_paused", True),
            ("cooling_humidity_resume_pending", True),
            ("heating_excess_deadline", 0), ("hot_water_low_deadline", 1),
            ("future_profile_deadline", 0), ("hot_water_exit_mode", "auto"),
            ("control_warning", "failed restore"),
            ("heating_preset", "vacation"), ("hot_water_mode", "evening"),
        ):
            with self.subTest(key=key):
                journal = restored_journal()
                journal["control"][key] = value
                before = deepcopy(journal)
                self.assertIsNotNone(module.legacy_control_problem({}, journal))
                self.assertEqual(journal, before)

    def test_active_modules_do_not_import_removed_policy(self):
        for path in INTEGRATION.glob("*.py"):
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if isinstance(node, ast.ImportFrom):
                    self.assertNotIn("genesis_policy", node.module or "")
                    self.assertNotEqual(node.module, "managed_control")
        self.assertFalse((INTEGRATION / "managed_control.py").exists())
        self.assertFalse((INTEGRATION / "vendor/genesis_policy/control.py").exists())

    def test_room_controller_and_options_flow_are_removed(self):
        for filename, removed in (
            ("climate.py", "ThermiaCalibraRoomClimate"),
            ("config_flow.py", "ThermiaCalibraOptionsFlow"),
        ):
            tree = ast.parse((INTEGRATION / filename).read_text(encoding="utf-8"))
            self.assertNotIn(removed, {node.name for node in ast.walk(tree) if isinstance(node, ast.ClassDef)})


if __name__ == "__main__":
    unittest.main()
