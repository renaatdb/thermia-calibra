"""Thermia Genesis register, coil, and discrete-input models."""

from __future__ import annotations

from collections.abc import Callable
import math
from numbers import Real

from modbus_connection.model import Component, coil, discrete_input, gauge, integer, uint32

from .native_settings import NATIVE_SETTINGS, validate_native_setting

THERMIA_MISSING_VALUE = 0x4E20


def _native_setting_gauge(key: str):
    spec = NATIVE_SETTINGS[key]
    return gauge(
        spec.address,
        0.01,
        nan=THERMIA_MISSING_VALUE,
        writable=lambda value: validate_native_setting(key, value),
    )


def _range_validator(
    min_value: float, max_value: float, *, step: float = 0.01,
) -> Callable[[float], float]:
    def validator(value: float) -> float:
        if isinstance(value, bool) or not isinstance(value, Real) or not math.isfinite(value):
            raise ValueError("Thermia controls require finite numeric values")
        numeric_value = float(value)
        if not min_value <= numeric_value <= max_value:
            raise ValueError(
                f"{numeric_value} outside allowed range {min_value}..{max_value}"
            )
        if not math.isclose(numeric_value / step, round(numeric_value / step), rel_tol=0, abs_tol=1e-8):
            raise ValueError(f"Thermia control requires {step} steps")
        return numeric_value

    return validator


class GenesisCoils(Component):
    """Writable Thermia Genesis coil states used for visible controls."""

    max_gap = 0

    enable_tap_water = coil(8, writable=True)
    """Enable tap water production."""

    enable_heat = coil(9, writable=True)
    """Enable heating."""

    enable_anti_legionella = coil(24, writable=True)
    """Enable anti-legionella cycle."""

    enable_additional_heater_only = coil(25, writable=True)
    """Enable additional-heater-only operation."""

    enable_passive_cooling = coil(33, writable=True)
    """Enable passive cooling."""


class GenesisInputRegisters(Component):
    """Read-only Thermia Genesis input registers."""

    register_space = "input"
    max_gap = 0

    first_prioritised_demand = integer(1, nan=THERMIA_MISSING_VALUE)
    """Currently prioritised heat-pump demand."""

    compressor_speed_rpm = integer(5, nan=THERMIA_MISSING_VALUE)
    """Compressor speed."""

    condenser_in_temperature = gauge(8, 0.01, nan=THERMIA_MISSING_VALUE)
    """Condenser in temperature."""

    condenser_out_temperature = gauge(9, 0.01, nan=THERMIA_MISSING_VALUE)
    """Condenser out temperature."""

    brine_in_temperature = gauge(10, 0.01, nan=THERMIA_MISSING_VALUE)
    """Brine in temperature."""

    brine_out_temperature = gauge(11, 0.01, nan=THERMIA_MISSING_VALUE)
    """Brine out temperature."""

    system_supply_line_temperature = gauge(12, 0.01, nan=THERMIA_MISSING_VALUE)
    """System supply line temperature."""

    outdoor_temperature = gauge(13, 0.01, nan=THERMIA_MISSING_VALUE)
    """Outdoor temperature."""

    tap_water_top_temperature = gauge(15, 0.01, nan=THERMIA_MISSING_VALUE)
    """Tap water top temperature."""

    tap_water_lower_temperature = gauge(16, 0.01, nan=THERMIA_MISSING_VALUE)
    """Tap water lower temperature."""

    tap_water_weighted_temperature = gauge(17, 0.01, nan=THERMIA_MISSING_VALUE)
    """Tap water weighted temperature."""

    system_supply_line_calculated_set_point = gauge(
        18,
        0.01,
        nan=THERMIA_MISSING_VALUE,
    )
    """Calculated system supply line set point."""

    system_return_line_temperature = gauge(27, 0.01, nan=THERMIA_MISSING_VALUE)
    """System return line temperature."""

    condenser_circulation_pump_speed = gauge(39, 0.01, nan=THERMIA_MISSING_VALUE)
    """Condenser circulation pump speed."""

    brine_circulation_pump_speed = gauge(44, 0.01, nan=THERMIA_MISSING_VALUE)
    """Brine circulation pump speed."""

    tap_water_valve_position = integer(47, nan=THERMIA_MISSING_VALUE)
    """Tap water directional valve position."""

    compressor_operating_hours = uint32(48)
    """Compressor operating hours."""

    tap_water_operating_hours = uint32(50)
    """Tap water operating hours."""

    external_additional_heater_operating_hours = uint32(52)
    """External additional heater operating hours."""

    compressor_speed_percent = gauge(54, 0.01, nan=THERMIA_MISSING_VALUE)
    """Compressor speed percentage."""

    compressor_current_gear = gauge(61, 0.01, nan=THERMIA_MISSING_VALUE)
    """Current compressor gear."""

    mix_valve_cooling_opening_degree = integer(137, nan=THERMIA_MISSING_VALUE)
    """Mix valve cooling opening degree."""


class GenesisDiscreteInputs(Component):
    """Read-only Thermia Genesis discrete inputs."""

    max_gap = 0

    alarm_active_class_a = discrete_input(0)
    """Class A alarm active."""

    alarm_active_class_b = discrete_input(1)
    """Class B alarm active."""

    alarm_active_class_c = discrete_input(2)
    """Class C alarm active."""

    maximum_time_for_anti_legionella_exceeded = discrete_input(82)
    """Anti-legionella maximum-time alarm."""


class GenesisHoldingRegisters(Component):
    """Thermia Genesis holding registers used for sensors and controls."""

    register_space = "holding"
    max_gap = 0

    comfort_wheel_setting = gauge(
        5,
        0.01,
        nan=THERMIA_MISSING_VALUE,
        writable=_range_validator(10, 40),
    )
    """Comfort wheel setting as the user-facing temperature."""

    start_temperature_tap_water = gauge(
        22,
        0.01,
        nan=THERMIA_MISSING_VALUE,
        writable=_range_validator(20, 65),
    )
    """Tap water start temperature."""

    stop_temperature_tap_water = gauge(
        23,
        0.01,
        nan=THERMIA_MISSING_VALUE,
        writable=_range_validator(30, 70),
    )
    """Tap water stop temperature."""

    cooling_start_temperature = gauge(
        105,
        0.01,
        nan=THERMIA_MISSING_VALUE,
    )
    """Cooling start temperature."""

    cooling_stop_temperature = gauge(
        106,
        0.01,
        nan=THERMIA_MISSING_VALUE,
    )
    """Cooling stop temperature."""

    outdoor_temperature_source = integer(
        117,
        writable=_range_validator(0, 1, step=1),
    )
    """Outdoor temperature source: 0 = physical PT1000, 1 = BMS."""

    bms_outdoor_temperature = gauge(
        118,
        0.01,
        nan=THERMIA_MISSING_VALUE,
        writable=_range_validator(-50, 200),
    )
    """Outdoor temperature supplied through BMS."""

    heating_season_stop_temperature = _native_setting_gauge(
        "heating_season_stop_temperature"
    )
    """Heating season stop temperature."""

    cooling_minimum_outdoor_temperature_permitted = gauge(
        303,
        0.01,
        nan=THERMIA_MISSING_VALUE,
    )
    """Minimum outdoor temperature at which cooling is permitted."""

    mix_valve_1_selected_mode = integer(298)
    """Selected mode for mix valve 1."""


class GenesisHeatingSettings(Component):
    """Optional heating limits and the seven native curve supply points."""

    register_space = "holding"
    max_gap = 0
    register_ranges = ((3, 4), (6, 12))

    max_supply_temperature = _native_setting_gauge("max_supply_temperature")
    min_supply_temperature = _native_setting_gauge("min_supply_temperature")
    heat_curve_supply_1 = _native_setting_gauge("heat_curve_supply_1")
    heat_curve_supply_2 = _native_setting_gauge("heat_curve_supply_2")
    heat_curve_supply_3 = _native_setting_gauge("heat_curve_supply_3")
    heat_curve_supply_4 = _native_setting_gauge("heat_curve_supply_4")
    heat_curve_supply_5 = _native_setting_gauge("heat_curve_supply_5")
    heat_curve_supply_6 = _native_setting_gauge("heat_curve_supply_6")
    heat_curve_supply_7 = _native_setting_gauge("heat_curve_supply_7")


class GenesisHeatingCurveInputs(Component):
    """Optional outdoor temperatures corresponding to the seven curve points."""

    register_space = "input"
    max_gap = 0
    register_ranges = ((20, 26),)

    heat_curve_outdoor_1 = gauge(20, 0.01, nan=THERMIA_MISSING_VALUE)
    heat_curve_outdoor_2 = gauge(21, 0.01, nan=THERMIA_MISSING_VALUE)
    heat_curve_outdoor_3 = gauge(22, 0.01, nan=THERMIA_MISSING_VALUE)
    heat_curve_outdoor_4 = gauge(23, 0.01, nan=THERMIA_MISSING_VALUE)
    heat_curve_outdoor_5 = gauge(24, 0.01, nan=THERMIA_MISSING_VALUE)
    heat_curve_outdoor_6 = gauge(25, 0.01, nan=THERMIA_MISSING_VALUE)
    heat_curve_outdoor_7 = gauge(26, 0.01, nan=THERMIA_MISSING_VALUE)


class GenesisCoolingSettings(Component):
    """Optional native setpoint for passive-cooling mixing valve 1."""

    register_space = "holding"
    max_gap = 0

    passive_cooling_supply_target = _native_setting_gauge("passive_cooling_supply_target")


class GenesisHotWaterRegisters(Component):
    """Thermia Genesis hot-water control registers from Thermia debug data."""

    register_space = "holding"
    max_gap = 0

    hot_water_boost = gauge(
        6257,
        1,
        nan=THERMIA_MISSING_VALUE,
        writable=_range_validator(0, 1, step=1),
    )
    """Hot water boost request."""
