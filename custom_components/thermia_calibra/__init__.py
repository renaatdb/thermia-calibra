"""Thermia Calibra Home Assistant integration."""

from __future__ import annotations

from homeassistant.components.modbus import async_get_unit
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST, CONF_PORT, Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryError
from homeassistant.helpers.storage import Store
from modbus_connection import ModbusTcpParams

from .const import CONF_UNIT_ID, DOMAIN, PLATFORMS
from .coordinator import ThermiaCalibraCoordinator
from .legacy_control import legacy_control_problem
from .vendor.thermia_calibra_modbus import ThermiaCalibra


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Thermia Calibra from a config entry."""
    # Check before opening the pump connection; preserve the old journal unchanged.
    saved = await Store(hass, 1, f"{DOMAIN}.{entry.entry_id}.thermostats").async_load()
    if problem := legacy_control_problem(entry.options, saved):
        raise ConfigEntryError(
            f"{problem}. Return to 0.1.12b2, inspect the pump and safely disable "
            "the old thermostat controller before upgrading. "
            "The saved recovery journal has not been changed."
        )
    params = ModbusTcpParams(
        host=entry.data[CONF_HOST],
        port=entry.data[CONF_PORT],
    )
    unit = async_get_unit(hass, entry, params, entry.data[CONF_UNIT_ID])
    device = ThermiaCalibra(unit)
    coordinator = ThermiaCalibraCoordinator(hass, entry, device)

    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = coordinator

    await hass.config_entries.async_forward_entry_setups(
        entry,
        [Platform(platform) for platform in PLATFORMS],
    )
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload Thermia Calibra."""
    return await hass.config_entries.async_unload_platforms(
        entry,
        [Platform(platform) for platform in PLATFORMS],
    )
