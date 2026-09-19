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
from homeassistant.core import HomeAssistant
from modbus_connection import ModbusError, ModbusTcpParams

from .const import CONF_UNIT_ID, DEFAULT_NAME, DEFAULT_PORT, DEFAULT_UNIT_ID, DOMAIN
from .vendor.thermia_calibra_modbus import ThermiaCalibra


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
