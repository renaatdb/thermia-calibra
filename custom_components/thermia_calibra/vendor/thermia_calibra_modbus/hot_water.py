"""Validation for the optional native hot-water thermostat."""

from __future__ import annotations

import math
from numbers import Real

START_FIELD = "start_temperature_tap_water"
STOP_FIELD = "stop_temperature_tap_water"
START_MIN, START_MAX = 20.0, 65.0
STOP_MIN, STOP_MAX = 30.0, 70.0
TEMPERATURE_STEP = 0.5


def validate_hot_water_range(
    start: float, stop: float, *, check_step: bool = True
) -> tuple[float, float]:
    """Validate software bounds, not asserted manufacturer limits."""
    for value, minimum, maximum in (
        (start, START_MIN, START_MAX), (stop, STOP_MIN, STOP_MAX)
    ):
        if (
            isinstance(value, bool)
            or not isinstance(value, Real)
            or not math.isfinite(value)
        ):
            raise ValueError("Hot-water temperatures must be finite numbers")
        if not minimum <= value <= maximum:
            raise ValueError(f"Hot-water temperature outside {minimum}..{maximum} C")
        if check_step and not math.isclose(
            value / TEMPERATURE_STEP,
            round(value / TEMPERATURE_STEP),
            abs_tol=1e-8,
            rel_tol=0,
        ):
            raise ValueError("Hot-water thermostat requires 0.5 C steps")
    if start >= stop:
        raise ValueError("Hot-water start temperature must be below stop temperature")
    return float(start), float(stop)
