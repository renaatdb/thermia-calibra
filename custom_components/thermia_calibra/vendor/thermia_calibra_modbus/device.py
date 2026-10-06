"""Top-level Thermia Calibra device object."""

from __future__ import annotations

import asyncio
import math
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from modbus_connection import ModbusConnectionError, ModbusError, ModbusTimeoutError

from .hot_water import START_FIELD, STOP_FIELD, validate_hot_water_range
from .native_settings import NATIVE_SETTINGS, validate_native_setting
from .readings import (
    GenesisCoils,
    GenesisCoolingSettings,
    GenesisDiscreteInputs,
    GenesisHeatingCurveInputs,
    GenesisHeatingSettings,
    GenesisHoldingRegisters,
    GenesisHotWaterRegisters,
    GenesisInputRegisters,
)

if TYPE_CHECKING:
    from modbus_connection import ModbusUnit


@dataclass
class UpdateReport:
    """Result of one device poll."""

    updated: list[str] = field(default_factory=list)
    failed: dict[str, ModbusError] = field(default_factory=dict)


class ThermiaCalibra:
    """A Thermia Calibra / Genesis heat pump reached through a Modbus unit."""

    def __init__(self, unit: ModbusUnit) -> None:
        self.unit = unit
        self.coils = GenesisCoils(unit)
        self.input_registers = GenesisInputRegisters(unit)
        self.holding_registers = GenesisHoldingRegisters(unit)
        self.discrete_inputs = GenesisDiscreteInputs(unit)
        self.hot_water_registers = GenesisHotWaterRegisters(unit)
        self.heating_settings = GenesisHeatingSettings(unit)
        self.heating_curve_inputs = GenesisHeatingCurveInputs(unit)
        self.cooling_settings = GenesisCoolingSettings(unit)
        self._native_write_lock = asyncio.Lock()
        self._hot_water_write_lock = asyncio.Lock()

    HEATPUMP_STATUS_BY_CODE = {
        1: "Manual operation",
        2: "Defrost",
        3: "Hot water",
        4: "Heat",
        5: "Active Cooling",
        6: "Pool",
        7: "Anti legionella",
        8: "Passive Cooling",
        98: "Standby",
        99: "No demand",
        100: "OFF",
    }

    @property
    def _demand_code(self) -> int | None:
        """Accept only the integer supplied by the demand register."""
        value = self.input_registers.first_prioritised_demand
        if isinstance(value, bool) or not isinstance(value, int):
            return None
        return value

    @property
    def heatpump_status(self) -> str | None:
        """Return the currently prioritised heat-pump demand as text."""
        code = self._demand_code
        if code is None:
            return None
        return self.HEATPUMP_STATUS_BY_CODE.get(code, f"Unknown ({code})")

    def _demand_is(self, wanted: int) -> bool | None:
        """An unrecognised demand must not look like an inactive subsystem."""
        code = self._demand_code
        if code not in self.HEATPUMP_STATUS_BY_CODE:
            return None
        return code == wanted

    @property
    def hot_water_operational(self) -> bool | None:
        """Return whether tap-water production is currently active."""
        return self._demand_is(3)

    @property
    def heat_operational(self) -> bool | None:
        """Return whether space heating is currently active."""
        return self._demand_is(4)

    @property
    def anti_legionella_operational(self) -> bool | None:
        """Return whether the anti-legionella cycle is currently active."""
        return self._demand_is(7)

    @property
    def active_alarms(self) -> int | None:
        """Return the number of active alarm classes."""
        alarm_values = (
            self.discrete_inputs.alarm_active_class_a,
            self.discrete_inputs.alarm_active_class_b,
            self.discrete_inputs.alarm_active_class_c,
        )
        if any(value is None for value in alarm_values):
            return None
        return sum(bool(value) for value in alarm_values)

    @property
    def passive_cooling_active(self) -> bool | None:
        """Return whether passive cooling appears to be actively running."""
        valve_opening = self.input_registers.mix_valve_cooling_opening_degree
        compressor_rpm = self.input_registers.compressor_speed_rpm
        if any(
            isinstance(value, bool)
            or not isinstance(value, (int, float))
            or not math.isfinite(value)
            for value in (valve_opening, compressor_rpm)
        ):
            return None
        if not 0 <= valve_opening <= 100 or compressor_rpm < 0:
            return None
        return valve_opening > 0 and compressor_rpm == 0

    async def async_update_readings(self) -> UpdateReport:
        """Refresh all modelled readings and control states."""
        report = UpdateReport()
        await self._async_update_component("input_registers", self.input_registers, report)
        await self._async_update_component("holding_registers", self.holding_registers, report)
        await self._async_update_component("discrete_inputs", self.discrete_inputs, report)
        await self._async_update_component("coils", self.coils, report)
        await self._async_update_component(
            "hot_water_registers",
            self.hot_water_registers,
            report,
        )
        for name in ("heating_settings", "heating_curve_inputs", "cooling_settings"):
            await self._async_update_component(name, getattr(self, name), report)
        return report

    async def async_write_coil(self, field: str, value: bool) -> None:
        """Write a boolean coil command and confirm its actual state."""
        if not isinstance(value, bool):
            raise ValueError("Thermia switch requests must be booleans")
        self._writable_field(self.coils, field)
        if field == "enable_tap_water":
            await self.async_write_hot_water_enabled(value)
            return
        async with self._native_write_lock:
            await self._async_write_verified(self.coils, field, value)

    async def async_write_holding_register(self, field: str, value: float) -> None:
        """Verify direct numbers and validate a boiler target against its sibling."""
        if field in NATIVE_SETTINGS:
            await self.async_write_native_setting(field, value)
            return
        value = self._validate_register_request(self.holding_registers, field, value)
        lock = (
            self._hot_water_write_lock if field in (START_FIELD, STOP_FIELD)
            else self._native_write_lock
        )
        async with lock:
            await self._async_write_verified(
                self.holding_registers, field, value,
                allow_missing_current=field == "bms_outdoor_temperature",
            )

    @staticmethod
    def _writable_field(component: Any, field: str) -> Any:
        resolved = component.resolved_fields.get(field)
        if resolved is None or not resolved.field.writable:
            raise AttributeError(f"{field!r} is unknown or read-only")
        return resolved.field

    def _validate_register_request(self, component: Any, field: str, value: float) -> float:
        definition = self._writable_field(component, field)
        value = definition.writable(value)
        encoded = definition.encode(value)
        if (
            definition.nan is not None and len(encoded) == 1
            and encoded[0] in definition.nan
        ):
            raise ValueError(f"{field} encodes as the controller's missing-value sentinel")
        return value

    @staticmethod
    def _matches_readback(actual: Any, expected: bool | float) -> bool:
        if isinstance(expected, bool):
            return actual is expected
        return (
            isinstance(actual, (int, float))
            and not isinstance(actual, bool)
            and math.isfinite(actual)
            and math.isclose(actual, expected, rel_tol=0, abs_tol=0.005)
        )

    async def _async_write_verified(
        self, component: Any, field: str, value: bool | float, *,
        allow_missing_current: bool = False, skip_unchanged: bool = False,
    ) -> None:
        """Confirm one explicit command without retries, rollback or policy writes."""
        await component.async_update(notify=False)
        current = getattr(component, field)
        valid_current = (
            isinstance(current, bool) if isinstance(value, bool)
            else isinstance(current, (int, float))
            and not isinstance(current, bool) and math.isfinite(current)
        )
        if not valid_current and not (
            allow_missing_current and current is None
        ):
            raise ValueError(f"{field} has no valid controller readback")
        expected = {field: value}
        if component is self.holding_registers and field in (START_FIELD, STOP_FIELD):
            expected = {
                START_FIELD: component.start_temperature_tap_water,
                STOP_FIELD: component.stop_temperature_tap_water,
            }
            expected[field] = value
            validate_hot_water_range(
                expected[START_FIELD], expected[STOP_FIELD], check_step=False,
            )
        if skip_unchanged and self._matches_readback(current, value):
            return
        await component.write(field, value)
        await component.async_update(notify=False)
        if any(
            not self._matches_readback(getattr(component, name), wanted)
            for name, wanted in expected.items()
        ):
            raise ValueError(
                f"{field} write was not confirmed by the controller; check actual settings"
            )
        component.notify()

    async def async_write_hot_water_range(self, start: float, stop: float) -> None:
        """Verify a paired change while keeping every intermediate range valid."""
        start, stop = validate_hot_water_range(start, stop)
        component = self.holding_registers
        async with self._hot_water_write_lock:
            await component.async_update(notify=False)
            expected = validate_hot_water_range(
                component.start_temperature_tap_water,
                component.stop_temperature_tap_water,
                check_step=False,
            )
            # Raise the stop first when the new start crosses the old stop.
            changes = [(START_FIELD, start), (STOP_FIELD, stop)]
            if start >= expected[1]:
                changes.reverse()
            for field, value in changes:
                index = 0 if field == START_FIELD else 1
                if math.isclose(expected[index], value, rel_tol=0, abs_tol=0.005):
                    continue
                await component.async_update(notify=False)
                actual = (
                    component.start_temperature_tap_water,
                    component.stop_temperature_tap_water,
                )
                if actual != expected:
                    raise ValueError(
                        "Hot-water settings changed during the request; "
                        "read the controller before retrying"
                    )
                candidate = list(expected)
                candidate[index] = value
                validate_hot_water_range(*candidate, check_step=False)
                await component.write(field, value)
                await component.async_update(notify=False)
                actual = (
                    component.start_temperature_tap_water,
                    component.stop_temperature_tap_water,
                )
                if any(
                    value is None
                    or not math.isclose(value, wanted, rel_tol=0, abs_tol=0.005)
                    for value, wanted in zip(actual, candidate)
                ):
                    raise ValueError(
                        "Hot-water write was not confirmed; "
                        "the range may be partially changed"
                    )
                expected = tuple(candidate)
            component.notify()

    async def async_write_hot_water_enabled(self, enabled: bool) -> None:
        """Verify the normal tap-water enable coil without changing other modes."""
        if not isinstance(enabled, bool):
            raise ValueError("Hot-water enable must be a boolean")
        async with self._hot_water_write_lock:
            await self._async_write_verified(
                self.coils, "enable_tap_water", enabled, skip_unchanged=True,
            )

    async def async_write_hot_water_register(self, field: str, value: float) -> None:
        """Write an explicit Boost request and confirm the request register."""
        value = self._validate_register_request(self.hot_water_registers, field, value)
        async with self._native_write_lock:
            await self._async_write_verified(self.hot_water_registers, field, value)

    async def async_write_native_setting(self, field: str, value: float) -> None:
        """Read, validate, write and verify one supported native setting."""
        value = validate_native_setting(field, value)
        spec = NATIVE_SETTINGS[field]
        component = getattr(self, spec.report_name)
        async with self._native_write_lock:
            await component.async_update(notify=False)
            current = getattr(component, field)
            if current is None or not math.isfinite(current):
                raise ValueError(f"{spec.name} has no valid controller readback")

            if field in ("min_supply_temperature", "max_supply_temperature"):
                minimum = (
                    value if field == "min_supply_temperature"
                    else component.min_supply_temperature
                )
                maximum = (
                    value if field == "max_supply_temperature"
                    else component.max_supply_temperature
                )
                if minimum is None or maximum is None or minimum > maximum:
                    raise ValueError("Heating supply minimum must not exceed maximum")

            await component.write(field, value)
            await component.async_update(notify=False)
            actual = getattr(component, field)
            if actual is None or not math.isclose(actual, value, rel_tol=0, abs_tol=0.005):
                raise ValueError(f"{spec.name} write was not confirmed by the controller")
            component.notify()

    async def _async_update_component(
        self,
        name: str,
        component: Any,
        report: UpdateReport,
    ) -> None:
        """Refresh one register group and keep partial successes usable."""
        try:
            await component.async_update(notify=False)
        except ModbusConnectionError:
            raise
        except ModbusTimeoutError as err:
            if not report.updated and not report.failed:
                raise
            report.failed[name] = err
        except ModbusError as err:
            report.failed[name] = err
        else:
            report.updated.append(name)
            component.notify()

    async def async_update(self) -> UpdateReport:
        """Refresh all currently modelled data."""
        return await self.async_update_readings()
