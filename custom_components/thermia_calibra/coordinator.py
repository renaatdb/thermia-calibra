"""Data coordinator for Thermia Calibra."""

from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from modbus_connection import ModbusError

from .const import DOMAIN, SCAN_INTERVAL
from .vendor.thermia_calibra_modbus import ThermiaCalibra, UpdateReport

_LOGGER = logging.getLogger(__name__)


class ThermiaCalibraCoordinator(DataUpdateCoordinator[UpdateReport]):
    """Poll the Thermia Calibra device."""

    def __init__(
        self,
        hass: HomeAssistant,
        entry: ConfigEntry,
        device: ThermiaCalibra,
    ) -> None:
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=DOMAIN,
            update_interval=SCAN_INTERVAL,
        )
        self.device = device
        self._failed: frozenset[str] = frozenset()

    async def _async_update_data(self) -> UpdateReport:
        """Fetch data from the heat pump."""
        try:
            report = await self.device.async_update_readings()
        except ModbusError as err:
            raise UpdateFailed(str(err)) from err

        if not report.updated:
            errors = list(report.failed.values())
            if errors:
                raise UpdateFailed(f"no Thermia subsystem answered: {errors[0]}") from errors[0]
            raise UpdateFailed("no Thermia subsystem answered")

        for name in sorted(report.failed.keys() - self._failed):
            _LOGGER.warning("Failed to fetch %s: %s", name, report.failed[name])
        self._failed = frozenset(report.failed)
        return report

    async def async_write_coil(self, field: str, value: bool) -> None:
        """Write a Thermia coil and refresh Home Assistant state."""
        try:
            await self.device.async_write_coil(field, value)
        except (AttributeError, ModbusError, ValueError) as err:
            raise HomeAssistantError(f"Failed to write Thermia switch {field}") from err

        await self.async_request_refresh()

    async def async_write_holding_register(self, field: str, value: float) -> None:
        """Write a Thermia holding register and refresh Home Assistant state."""
        try:
            await self.device.async_write_holding_register(field, value)
        except (AttributeError, ModbusError, ValueError) as err:
            raise HomeAssistantError(f"Failed to write Thermia number {field}") from err

        await self.async_request_refresh()

    async def async_write_hot_water_register(self, field: str, value: float) -> None:
        """Write a Thermia hot-water register and refresh Home Assistant state."""
        try:
            await self.device.async_write_hot_water_register(field, value)
        except (AttributeError, ModbusError, ValueError) as err:
            raise HomeAssistantError(
                f"Failed to write Thermia hot-water control {field}"
            ) from err

        await self.async_request_refresh()
