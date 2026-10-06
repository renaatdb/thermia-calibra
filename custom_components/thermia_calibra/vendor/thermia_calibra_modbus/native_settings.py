"""Genesis 17.1 native settings with integration-level temperature limits.

Adapted from thermia-genesis-modbus 0.1.9; see THIRD_PARTY_LICENSE.
"""

from __future__ import annotations

import math
from dataclasses import dataclass


@dataclass(frozen=True)
class NativeSetting:
    """A native holding register and its software control limits."""

    key: str
    name: str
    address: int
    min_value: float
    max_value: float
    report_name: str
    step: float = 1.0


# ACMBDH01UG0402 defines addresses and Celsius x100, not permitted ranges.
NATIVE_SETTINGS = {
    item.key: item
    for item in (
        NativeSetting(
            "heating_season_stop_temperature", "Heating Season Stop Temperature",
            16, -10, 40, "holding_registers",
        ),
        NativeSetting(
            "min_supply_temperature", "Minimum Heating Supply Temperature",
            4, 5, 65, "heating_settings",
        ),
        NativeSetting(
            "max_supply_temperature", "Maximum Heating Supply Temperature",
            3, 5, 65, "heating_settings",
        ),
        *(
            NativeSetting(
                f"heat_curve_supply_{i + 1}", f"Heating Curve Supply Point {i + 1}",
                6 + i, 5, 65, "heating_settings",
            )
            for i in range(7)
        ),
        NativeSetting(
            "passive_cooling_supply_target", "Passive Cooling Supply Target",
            302, 5, 30, "cooling_settings",
        ),
    )
}


def validate_native_setting(key: str, value: float) -> float:
    """Reject invalid values before they reach the Modbus transport."""
    if key not in NATIVE_SETTINGS:
        raise ValueError(f"Unsupported native setting: {key}")
    spec = NATIVE_SETTINGS[key]
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{spec.name} requires a numeric temperature")
    result = float(value)
    if not math.isfinite(result) or not spec.min_value <= result <= spec.max_value:
        raise ValueError(
            f"{spec.name} must be between {spec.min_value:g} and {spec.max_value:g} C"
        )
    steps = (result - spec.min_value) / spec.step
    if not math.isclose(steps, round(steps), rel_tol=0, abs_tol=1e-8):
        raise ValueError(f"{spec.name} requires {spec.step:g} C steps")
    return result
