"""Data coordinator for Thermia Calibra."""

from __future__ import annotations

import asyncio
import logging
from contextlib import nullcontext

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.helpers.storage import Store
from homeassistant.util import dt as dt_util
from modbus_connection import ModbusError

from .const import DOMAIN, SCAN_INTERVAL
from .vendor.thermia_calibra_modbus import ThermiaCalibra, UpdateReport
from .managed_control import ManagedControl
from .vendor.genesis_policy.temperature import temperature_sample, valid_temperature
from .vendor.genesis_policy.humidity import humidity_sample

_LOGGER = logging.getLogger(__name__)


async def _device_call(coordinator, method, *args):
    async with getattr(coordinator, "_io_lock", nullcontext()):
        return await method(*args)


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
        self.entry = entry
        self._io_lock = asyncio.Lock()
        self._control_store = Store(hass, 1, f"{DOMAIN}.{entry.entry_id}.thermostats")
        self.control = ManagedControl(device.unit, dict(entry.options), self._control_store.async_save)
        self.control_error = None
        self._failed: frozenset[str] = frozenset()

    async def async_load_control(self):
        saved = await self._control_store.async_load()
        self.control = ManagedControl(
            self.device.unit, dict(self.entry.options), self._control_store.async_save, saved
        )

    @property
    def controller_enabled(self):
        return self.control.enabled

    @property
    def engine(self):
        return self.control.engine

    @property
    def effective_inside(self):
        entity_id = self.control.options.get("inside_sensor")
        if entity_id:
            return temperature_sample(
                self.hass.states.get(entity_id), dt_util.utcnow(),
                self.control.options["sensor_timeout"], inside=True,
            ).value
        if self.control.value("room_sensor_alarm") is not False:
            return None
        return valid_temperature(self.control.value("indoor_temperature"), inside=True)

    @property
    def effective_inside_humidity(self):
        entity_id = self.control.options.get("inside_humidity_sensor")
        return humidity_sample(
            self.hass.states.get(entity_id), dt_util.utcnow(),
            self.control.options["sensor_timeout"],
        ).value if entity_id else None

    @property
    def effective_outside(self):
        if self.controller_enabled:
            return valid_temperature(self.control.value("outdoor_temperature"))
        if self.data and "input_registers" in self.data.updated:
            return valid_temperature(self.device.input_registers.outdoor_temperature)
        return None

    async def async_control_command(self, action, value):
        try:
            async with self._io_lock:
                await self.control.command(
                    action, value, lambda: self.effective_inside, lambda: self.effective_outside,
                    lambda: self.effective_inside_humidity,
                )
                self.control_error = None
        except (ModbusError, ValueError, RuntimeError, OSError) as err:
            self.control_error = str(err)
            raise HomeAssistantError(f"Thermostat control failed: {err}") from err
        finally:
            await self.async_request_refresh()

    async def async_shutdown_control(self):
        async with self._io_lock:
            await self.control.shutdown()

    async def _async_update_data(self) -> UpdateReport:
        """Fetch data from the heat pump."""
        async with self._io_lock:
            report = await self._async_poll_device()
            self.data = report
            try:
                await self.control.update(
                    lambda: self.effective_inside, lambda: self.effective_outside,
                    lambda: self.effective_inside_humidity
                )
                self.control_error = None
            except (ModbusError, ValueError, RuntimeError, OSError) as err:
                self.control.ready = False
                if self.control_error != str(err):
                    _LOGGER.warning("Optional thermostat control paused: %s", err)
                self.control_error = str(err)
            return report

    async def _async_poll_device(self) -> UpdateReport:
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
            await _device_call(self, self.device.async_write_coil, field, value)
        except (AttributeError, ModbusError, ValueError) as err:
            raise HomeAssistantError(f"Failed to write Thermia switch {field}") from err

        await self.async_request_refresh()

    async def async_write_holding_register(self, field: str, value: float) -> None:
        """Write a Thermia holding register and refresh Home Assistant state."""
        try:
            await _device_call(self, self.device.async_write_holding_register, field, value)
        except (AttributeError, ModbusError, ValueError) as err:
            raise HomeAssistantError(f"Failed to write Thermia number {field}") from err

        await self.async_request_refresh()

    async def async_write_hot_water_register(self, field: str, value: float) -> None:
        """Write a Thermia hot-water register and refresh Home Assistant state."""
        try:
            await _device_call(self, self.device.async_write_hot_water_register, field, value)
        except (AttributeError, ModbusError, ValueError) as err:
            raise HomeAssistantError(
                f"Failed to write Thermia hot-water control {field}"
            ) from err

        await self.async_request_refresh()

    async def async_write_native_setting(self, field: str, value: float) -> None:
        """Write a native setting with controller readback verification."""
        try:
            await _device_call(self, self.device.async_write_native_setting, field, value)
        except (AttributeError, ModbusError, ValueError) as err:
            raise HomeAssistantError(
                f"Failed to write Thermia setting {field}: {err}"
            ) from err
        finally:
            await self.async_request_refresh()

    async def async_write_hot_water_range(self, start: float, stop: float) -> None:
        """Refresh actual state even when a paired write only partially succeeds."""
        try:
            await _device_call(self, self.device.async_write_hot_water_range, start, stop)
        except (AttributeError, ModbusError, ValueError) as err:
            raise HomeAssistantError(
                f"Failed to set Thermia hot-water range: {err}. "
                "Check both controller temperatures before retrying."
            ) from err
        finally:
            await self.async_request_refresh()

    async def async_write_hot_water_enabled(self, enabled: bool) -> None:
        """Write and verify the normal tap-water production mode."""
        try:
            await _device_call(self, self.device.async_write_hot_water_enabled, enabled)
        except (AttributeError, ModbusError, ValueError) as err:
            raise HomeAssistantError(f"Failed to set Thermia hot-water mode: {err}") from err
        finally:
            await self.async_request_refresh()
