"""Thermia Genesis register, coil, and discrete-input models."""

from __future__ import annotations

from collections.abc import Callable

from modbus_connection.model import Component, coil, discrete_input, gauge, integer, uint32

THERMIA_MISSING_VALUE = 0x4E20


def _range_validator(min_value: float, max_value: float) -> Callable[[float], float]:
    def validator(value: float) -> float:
        numeric_value = float(value)
        if not min_value <= numeric_value <= max_value:
            raise ValueError(
                f"{numeric_value} outside allowed range {min_value}..{max_value}"
            )
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

    cooling_start_temperature = gauge(105, 0.01, nan=THERMIA_MISSING_VALUE)
    """Cooling start temperature."""

    cooling_stop_temperature = gauge(106, 0.01, nan=THERMIA_MISSING_VALUE)
    """Cooling stop temperature."""

    heating_season_stop_temperature = gauge(16, 0.01, nan=THERMIA_MISSING_VALUE)
    """Heating season stop temperature."""

    cooling_minimum_outdoor_temperature_permitted = gauge(
        303,
        0.01,
        nan=THERMIA_MISSING_VALUE,
    )
    """Minimum outdoor temperature at which cooling is permitted."""

    mix_valve_1_selected_mode = integer(298)
    """Selected mode for mix valve 1."""


class GenesisHotWaterRegisters(Component):
    """Thermia Genesis hot-water control registers from Thermia debug data."""

    register_space = "holding"
    max_gap = 0

    hot_water_boost = gauge(
        6257,
        1,
        nan=THERMIA_MISSING_VALUE,
        writable=_range_validator(0, 1),
    )
    """Hot water boost request."""
