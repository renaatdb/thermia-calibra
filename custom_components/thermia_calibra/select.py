"""Thermia Calibra selection controls."""

from __future__ import annotations

from typing import ClassVar

from homeassistant.components.select import SelectEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST, CONF_PORT
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import CONF_UNIT_ID, DEVICE_MODEL, DEVICE_NAME, DOMAIN, MANUFACTURER
from .coordinator import ThermiaCalibraCoordinator

OPTION_PHYSICAL_SENSOR = "Physical outdoor sensor (PT1000)"
OPTION_EXTERNAL_MODBUS = "External outdoor temperature (Modbus)"

SOURCE_OPTION_BY_VALUE = {
    0: OPTION_PHYSICAL_SENSOR,
    1: OPTION_EXTERNAL_MODBUS,
}
SOURCE_VALUE_BY_OPTION = {
    option: value for value, option in SOURCE_OPTION_BY_VALUE.items()
}


class ThermiaCalibraOutdoorTemperatureSourceSelect(
    CoordinatorEntity[ThermiaCalibraCoordinator],
    SelectEntity,
):
    """Select the outdoor-temperature source used by the heat pump."""

    _attr_has_entity_name = True
    _attr_name = "Outdoor Temperature Source"
    _attr_icon = "mdi:thermometer-lines"
    _attr_options: ClassVar[list[str]] = list(SOURCE_VALUE_BY_OPTION)

    def __init__(
        self,
        coordinator: ThermiaCalibraCoordinator,
        entry: ConfigEntry,
    ) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{entry.entry_id}_outdoor_temperature_source"
        self._attr_device_info = DeviceInfo(
            identifiers={
                (
                    DOMAIN,
                    (
                        f"{entry.data[CONF_HOST]}:"
                        f"{entry.data[CONF_PORT]}:"
                        f"{entry.data[CONF_UNIT_ID]}"
                    ),
                )
            },
            manufacturer=MANUFACTURER,
            model=DEVICE_MODEL,
            name=DEVICE_NAME,
        )

    @property
    def available(self) -> bool:
        """Return whether the holding registers were refreshed."""
        return (
            super().available
            and self.coordinator.data is not None
            and "holding_registers" in self.coordinator.data.updated
        )

    @property
    def current_option(self) -> str | None:
        """Return the currently selected outdoor-temperature source."""
        value = self.coordinator.device.holding_registers.outdoor_temperature_source
        if value is None:
            return None
        return SOURCE_OPTION_BY_VALUE.get(int(value))

    async def async_select_option(self, option: str) -> None:
        """Select the outdoor-temperature source."""
        await self.coordinator.async_write_holding_register(
            "outdoor_temperature_source",
            SOURCE_VALUE_BY_OPTION[option],
        )


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the Thermia Calibra selects."""
    coordinator: ThermiaCalibraCoordinator = entry.runtime_data
    async_add_entities(
        [ThermiaCalibraOutdoorTemperatureSourceSelect(coordinator, entry)]
    )
