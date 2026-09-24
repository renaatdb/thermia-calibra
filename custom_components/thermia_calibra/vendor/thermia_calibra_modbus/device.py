"""Top-level Thermia Calibra device object."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from modbus_connection import ModbusConnectionError, ModbusError, ModbusTimeoutError

from .readings import (
    GenesisCoils,
    GenesisDiscreteInputs,
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
        self.coils = GenesisCoils(unit)
        self.input_registers = GenesisInputRegisters(unit)
        self.holding_registers = GenesisHoldingRegisters(unit)
        self.discrete_inputs = GenesisDiscreteInputs(unit)
        self.hot_water_registers = GenesisHotWaterRegisters(unit)

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
    def heatpump_status(self) -> str | None:
        """Return the currently prioritised heat-pump demand as text."""
        value = self.input_registers.first_prioritised_demand
        if value is None:
            return None

        try:
            code = int(value)
        except (TypeError, ValueError):
            return None

        return self.HEATPUMP_STATUS_BY_CODE.get(code, f"Unknown ({code})")

    @property
    def hot_water_operational(self) -> bool | None:
        """Return whether tap-water production is currently active."""
        status = self.heatpump_status
        if status is None:
            return None
        return status == "Hot water"

    @property
    def anti_legionella_operational(self) -> bool | None:
        """Return whether the anti-legionella cycle is currently active."""
        status = self.heatpump_status
        if status is None:
            return None
        return status == "Anti legionella"

    @property
    def active_alarms(self) -> int | None:
        """Return the number of active alarm classes."""
        alarm_values = (
            self.discrete_inputs.alarm_active_class_a,
            self.discrete_inputs.alarm_active_class_b,
            self.discrete_inputs.alarm_active_class_c,
        )
        if all(value is None for value in alarm_values):
            return None
        return sum(bool(value) for value in alarm_values)

    @property
    def passive_cooling_active(self) -> bool | None:
        """Return whether passive cooling appears to be actively running."""
        valve_opening = self.input_registers.mix_valve_cooling_opening_degree
        compressor_rpm = self.input_registers.compressor_speed_rpm
        if valve_opening is None or compressor_rpm is None:
            return None
        return float(valve_opening) > 0 and float(compressor_rpm) == 0

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
        return report

    async def async_write_coil(self, field: str, value: bool) -> None:
        """Write a Thermia coil control."""
        await self.coils.write(field, bool(value))

    async def async_write_holding_register(self, field: str, value: float) -> None:
        """Write a Thermia holding-register control."""
        await self.holding_registers.write(field, value)

    async def async_write_hot_water_register(self, field: str, value: float) -> None:
        """Write a Thermia hot-water control register."""
        await self.hot_water_registers.write(field, value)

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
