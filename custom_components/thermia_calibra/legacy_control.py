"""Read-only upgrade guard for the removed 0.1.12b2 thermostat controller."""

from collections.abc import Mapping
from typing import Any


def legacy_control_problem(options: Mapping[str, Any], saved: Any) -> str | None:
    """Never forget unresolved controller writes or attempt to restore them here."""
    if options.get("controller_enabled", False) is not False:
        return "The old automatic thermostat controller is still enabled"
    if saved is None or saved == {}:
        return None
    if not isinstance(saved, dict):
        return "The old thermostat journal is unreadable"
    if saved.get("blocked") or saved.get("ownership"):
        return "The old thermostat still has suspended or owned pump settings"
    if not isinstance(saved.get("ownership"), dict):
        return "The old thermostat ownership journal is incomplete"
    control = saved.get("control")
    if not isinstance(control, dict):
        return "The old thermostat recovery journal is incomplete"
    for key, expected_type in (
        ("overrides", dict), ("pending_restore", list), ("charge_active", dict),
    ):
        if not isinstance(control.get(key), expected_type):
            return "The old thermostat recovery journal is incomplete"
    if control["overrides"] or control["pending_restore"]:
        return "Temporary pump settings still need restoration"
    if any(control["charge_active"].values()) or control.get("sg_owners"):
        return "The old thermostat still owns a charging request"
    for key in (
        "boost_once", "boost_enabled", "native_boost_coupled",
        "cooling_humidity_paused", "cooling_humidity_resume_pending",
    ):
        if control.get(key):
            return "The old thermostat still has an unfinished temporary action"
    if any(value is not None for key, value in control.items() if key.endswith("_deadline")):
        return "The old thermostat still has a temporary preset deadline"
    if control.get("hot_water_exit_mode") is not None or control.get("control_warning"):
        return "The old thermostat still reports unresolved recovery"
    if control.get("heating_preset", "normal") != "normal" or control.get("hot_water_mode", "auto") not in ("auto", "off"):
        return "The old thermostat still has a temporary preset selected"
    return None
