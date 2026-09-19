"""Thermia Calibra Home Assistant integration."""

from __future__ import annotations

from homeassistant.components.modbus import async_get_unit
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST, CONF_PORT, Platform
from homeassistant.core import HomeAssistant
from modbus_connection import ModbusTcpParams

from .const import CONF_UNIT_ID, DOMAIN, PLATFORMS
from .coordinator import ThermiaCalibraCoordinator
from .vendor.thermia_calibra_modbus import ThermiaCalibra


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Thermia Calibra from a config entry."""
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
