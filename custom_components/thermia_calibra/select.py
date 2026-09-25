"""Thermia Calibra select controls."""

from __future__ import annotations

from homeassistant.components.select import SelectEntity, SelectEntityDescription
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST, CONF_PORT
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import CONF_UNIT_ID, DEVICE_MODEL, DEVICE_NAME, DOMAIN, MANUFACTURER
from .coordinator import ThermiaCalibraCoordinator

OPTION_PHYSICAL = "Physical PT1000"
OPTION_BMS = "BMS"

SOURCE_TO_VALUE = {
    OPTION_PHYSICAL: 0,
    OPTION_BMS: 1,
}

VALUE_TO_SOURCE = {
    0: OPTION_PHYSICAL,
    1: OPTION_BMS,
}

DESCRIPTION = SelectEntityDescription(
    key="outdoor_temperature_source_control",
    name="Outdoor Temperature Source",
    icon="mdi:thermometer-lines",
    options=[OPTION_PHYSICAL, OPTION_BMS],
)


class ThermiaCalibraOutdoorTemperatureSourceSelect(
    CoordinatorEntity[ThermiaCalibraCoordinator],
    SelectEntity,
):
    """Select the Thermia outdoor temperature source."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: ThermiaCalibraCoordinator,
        entry: ConfigEntry,
    ) -> None:
        super().__init__(coordinator)
        self.entity_description = DESCRIPTION
        self._attr_unique_id = (
            f"{entry.entry_id}_outdoor_temperature_source_control"
        )
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
        """Return the currently selected outdoor temperature source."""
        value = self.coordinator.device.holding_registers.outdoor_temperature_source
        if value is None:
            return None

        try:
            return VALUE_TO_SOURCE.get(int(value))
        except (TypeError, ValueError):
            return None

    async def async_select_option(self, option: str) -> None:
        """Set the Thermia outdoor temperature source."""
        if option not in SOURCE_TO_VALUE:
            raise ValueError(f"Unsupported outdoor temperature source: {option}")

        await self.coordinator.async_write_holding_register(
            "outdoor_temperature_source",
            SOURCE_TO_VALUE[option],
        )


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Thermia Calibra selects."""
    coordinator: ThermiaCalibraCoordinator = entry.runtime_data
    async_add_entities(
        [ThermiaCalibraOutdoorTemperatureSourceSelect(coordinator, entry)]
    )
