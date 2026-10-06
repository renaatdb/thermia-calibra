"""Config flow for Thermia Calibra."""

from __future__ import annotations

from typing import Any

import voluptuous as vol
from homeassistant.components.modbus import async_get_temporary_unit
from homeassistant import config_entries
from homeassistant.const import CONF_HOST, CONF_PORT
from homeassistant.exceptions import HomeAssistantError
from homeassistant.data_entry_flow import FlowResult
import homeassistant.helpers.config_validation as cv
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import selector
from modbus_connection import ModbusError, ModbusTcpParams

from .const import CONF_UNIT_ID, DEFAULT_NAME, DEFAULT_PORT, DEFAULT_UNIT_ID, DOMAIN
from .vendor.thermia_calibra_modbus import ThermiaCalibra
from .managed_control import DEFAULT_CONTROL_OPTIONS, control_options
from .vendor.genesis_policy.control import ControlEngine


class CannotConnect(Exception):
    """Raised when the Thermia does not answer any POC register group."""


async def _async_probe(
    hass: HomeAssistant,
    host: str,
    port: int,
    unit_id: int,
) -> None:
    """Check whether at least one known register group can be read."""
    async with async_get_temporary_unit(
        hass,
        ModbusTcpParams(host=host, port=port),
        unit_id,
    ) as unit:
        device = ThermiaCalibra(unit)
        report = await device.async_update_readings()

    if not report.updated:
        raise CannotConnect


class ThermiaCalibraConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a Thermia Calibra config flow."""

    VERSION = 1

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: config_entries.ConfigEntry):
        return ThermiaCalibraOptionsFlow()

    async def async_step_user(
        self,
        user_input: dict[str, Any] | None = None,
    ) -> FlowResult:
        """Create the entry from host, port and unit id."""
        errors: dict[str, str] = {}

        if user_input is not None:
            try:
                await _async_probe(
                    self.hass,
                    user_input[CONF_HOST],
                    user_input[CONF_PORT],
                    user_input[CONF_UNIT_ID],
                )
            except (CannotConnect, HomeAssistantError, ModbusError):
                errors["base"] = "cannot_connect"
            else:
                unique_id = (
                    f"{user_input[CONF_HOST]}:"
                    f"{user_input[CONF_PORT]}:"
                    f"{user_input[CONF_UNIT_ID]}"
                )
                await self.async_set_unique_id(unique_id)
                self._abort_if_unique_id_configured()
                return self.async_create_entry(title=DEFAULT_NAME, data=user_input)

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_HOST): cv.string,
                    vol.Optional(CONF_PORT, default=DEFAULT_PORT): cv.port,
                    vol.Optional(CONF_UNIT_ID, default=DEFAULT_UNIT_ID): cv.positive_int,
                }
            ),
            errors=errors,
        )


class ThermiaCalibraOptionsFlow(config_entries.OptionsFlow):
    """Require explicit ownership before enabling either automatic thermostat."""

    async def async_step_init(self, user_input=None):
        self._options = DEFAULT_CONTROL_OPTIONS | dict(self.config_entry.options)
        if user_input is not None:
            self._options.update(user_input)
            for key in ("inside_sensor", "inside_humidity_sensor"):
                self._options[key] = user_input.get(key) or ""
            return await self.async_step_profiles()
        schema = {
            vol.Required("controller_enabled", default=self._options["controller_enabled"]): bool,
            vol.Required("confirm_other_controllers_disabled", default=False): bool,
            vol.Optional("inside_sensor", description={"suggested_value": self._options["inside_sensor"] or None}): selector.EntitySelector(
                selector.EntitySelectorConfig(domain="sensor", device_class="temperature")
            ),
            vol.Optional("inside_humidity_sensor", description={"suggested_value": self._options["inside_humidity_sensor"] or None}): selector.EntitySelector(
                selector.EntitySelectorConfig(domain="sensor", device_class="humidity")
            ),
            vol.Required("sensor_timeout", default=self._options["sensor_timeout"]): vol.All(vol.Coerce(int), vol.Range(min=60, max=86400)),
            vol.Required("confirm_native_boost", default=self._options["confirm_native_boost"]): bool,
            vol.Optional("release_external_state", default=False): bool,
        }
        return self.async_show_form(step_id="init", data_schema=vol.Schema(schema))

    async def async_step_profiles(self, user_input=None):
        errors = {}
        ranges = {
            "heating_low_offset": (0, 10),
            "heating_vacation_temperature": (10, 35),
            "heating_vacation_cooling_offset": (0, 10),
            "max_heating_temperature": (10, 35),
            "charge_supply_temperature": (20, 60),
            "heating_excess_heat_stop_offset": (0, 20),
            "heating_excess_hours": (0.1, 168),
            "hot_water_excess_hours": (0.1, 168),
            "hot_water_low_hours": (0.1, 168),
            "hot_water_evening_start": (30, 59),
            "hot_water_evening_stop": (30, 60),
            "hot_water_hysteresis": (2, 20),
            "cooling_humidity_limit": (30, 90),
            "cooling_vacation_humidity_limit": (30, 90),
            "cooling_dew_point_margin": (1, 5),
        }
        if user_input is not None:
            self._options.update(user_input)
            try:
                options = control_options(self._options)
                validator = ControlEngine(lambda key: None, None, None, options)
                for key in ranges:
                    validator._validate_setting(key, options[key])
                coordinator = getattr(self.config_entry, "runtime_data", None)
                if coordinator:
                    if options.pop("release_external_state", False):
                        async with coordinator._io_lock:
                            await coordinator.control.release_after_external_change()
                    await coordinator.async_shutdown_control()
            except (ValueError, RuntimeError, OSError, ModbusError):
                errors["base"] = "invalid_control"
            else:
                options.pop("release_external_state", None)
                return self.async_create_entry(title="", data=options)
        schema = {
            vol.Required(key, default=self._options[key]): vol.All(vol.Coerce(float), vol.Range(min=low, max=high))
            for key, (low, high) in ranges.items()
        }
        schema[vol.Required("cooling_humidity_enabled", default=self._options["cooling_humidity_enabled"])] = bool
        return self.async_show_form(step_id="profiles", data_schema=vol.Schema(schema), errors=errors)
