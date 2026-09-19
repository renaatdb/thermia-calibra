"""Thermia Calibra numeric controls."""

from __future__ import annotations

from dataclasses import dataclass

from homeassistant.components.number import (
    NumberDeviceClass,
    NumberEntity,
    NumberEntityDescription,
    NumberMode,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST, CONF_PORT, UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import CONF_UNIT_ID, DEVICE_MODEL, DEVICE_NAME, DOMAIN, MANUFACTURER
from .coordinator import ThermiaCalibraCoordinator

NumberValue = int | float | None


@dataclass(frozen=True, kw_only=True)
class ThermiaCalibraNumberDescription(NumberEntityDescription):
    """Describe one Thermia Calibra numeric control."""

    field_name: str
    report_name: str = "holding_registers"


NUMBERS: tuple[ThermiaCalibraNumberDescription, ...] = (
    ThermiaCalibraNumberDescription(
        key="comfort_wheel_setting",
        name="Comfort Wheel Setting",
        device_class=NumberDeviceClass.TEMPERATURE,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        native_min_value=10,
        native_max_value=40,
        native_step=0.5,
        mode=NumberMode.SLIDER,
        field_name="comfort_wheel_setting",
    ),
    ThermiaCalibraNumberDescription(
        key="start_temperature_tap_water",
        name="Start Temperature Tap Water",
        device_class=NumberDeviceClass.TEMPERATURE,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        native_min_value=20,
        native_max_value=65,
        native_step=1,
        mode=NumberMode.SLIDER,
        field_name="start_temperature_tap_water",
    ),
    ThermiaCalibraNumberDescription(
        key="stop_temperature_tap_water",
        name="Stop Temperature Tap Water",
        device_class=NumberDeviceClass.TEMPERATURE,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        native_min_value=30,
        native_max_value=70,
        native_step=0.5,
        mode=NumberMode.SLIDER,
        field_name="stop_temperature_tap_water",
    ),
)


class ThermiaCalibraNumber(
    CoordinatorEntity[ThermiaCalibraCoordinator],
    NumberEntity,
):
    """Thermia Calibra writable number."""

    entity_description: ThermiaCalibraNumberDescription
    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: ThermiaCalibraCoordinator,
        entry: ConfigEntry,
        description: ThermiaCalibraNumberDescription,
    ) -> None:
        super().__init__(coordinator)
        self.entity_description = description
        self._attr_unique_id = f"{entry.entry_id}_{description.key}"
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
        """Return if the source register group was refreshed."""
        return (
            super().available
            and self.coordinator.data is not None
            and self.entity_description.report_name in self.coordinator.data.updated
        )

    @property
    def native_value(self) -> NumberValue:
        """Return the current number value."""
        return getattr(
            self.coordinator.device.holding_registers,
            self.entity_description.field_name,
        )

    async def async_set_native_value(self, value: float) -> None:
        """Write the selected number value."""
        await self.coordinator.async_write_holding_register(
            self.entity_description.field_name,
            value,
        )


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Thermia Calibra numbers."""
    coordinator: ThermiaCalibraCoordinator = entry.runtime_data
    async_add_entities(
        ThermiaCalibraNumber(coordinator, entry, description)
        for description in NUMBERS
    )
