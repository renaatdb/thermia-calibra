"""Thermia Calibra switch controls."""

from __future__ import annotations

from dataclasses import dataclass

from homeassistant.components.switch import SwitchEntity, SwitchEntityDescription
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST, CONF_PORT
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import CONF_UNIT_ID, DEVICE_MODEL, DEVICE_NAME, DOMAIN, MANUFACTURER
from .coordinator import ThermiaCalibraCoordinator


@dataclass(frozen=True, kw_only=True)
class ThermiaCalibraSwitchDescription(SwitchEntityDescription):
    """Describe one Thermia Calibra switch."""

    field_name: str
    report_name: str = "coils"
    component_name: str = "coils"
    write_method_name: str = "async_write_coil"
    on_value: bool | int = True
    off_value: bool | int = False


SWITCHES: tuple[ThermiaCalibraSwitchDescription, ...] = (
    ThermiaCalibraSwitchDescription(
        key="enable_tap_water",
        name="Enable Tap Water",
        icon="mdi:water-boiler",
        field_name="enable_tap_water",
    ),
    ThermiaCalibraSwitchDescription(
        key="hot_water_boost",
        name="Hot Water Boost",
        icon="mdi:water-boiler-alert",
        field_name="hot_water_boost",
        report_name="hot_water_registers",
        component_name="hot_water_registers",
        write_method_name="async_write_hot_water_register",
        on_value=1,
        off_value=0,
    ),
    ThermiaCalibraSwitchDescription(
        key="enable_heat",
        name="Enable Heat",
        icon="mdi:radiator",
        field_name="enable_heat",
    ),
    ThermiaCalibraSwitchDescription(
        key="enable_passive_cooling",
        name="Enable Passive Cooling",
        icon="mdi:snowflake",
        field_name="enable_passive_cooling",
    ),
    ThermiaCalibraSwitchDescription(
        key="enable_anti_legionella",
        name="Enable Anti Legionella",
        icon="mdi:shield-check",
        field_name="enable_anti_legionella",
    ),
    ThermiaCalibraSwitchDescription(
        key="enable_additional_heater_only",
        name="Enable Additional Heater Only",
        icon="mdi:heat-wave",
        entity_registry_enabled_default=False,
        field_name="enable_additional_heater_only",
    ),
)


class ThermiaCalibraSwitch(
    CoordinatorEntity[ThermiaCalibraCoordinator],
    SwitchEntity,
):
    """Thermia Calibra writable switch."""

    entity_description: ThermiaCalibraSwitchDescription
    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: ThermiaCalibraCoordinator,
        entry: ConfigEntry,
        description: ThermiaCalibraSwitchDescription,
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
    def is_on(self) -> bool | None:
        """Return the switch state."""
        component = getattr(
            self.coordinator.device,
            self.entity_description.component_name,
        )
        value = getattr(
            component,
            self.entity_description.field_name,
        )
        if value is None:
            return None
        return bool(value)

    async def async_turn_on(self, **kwargs: object) -> None:
        """Turn on this Thermia switch."""
        write_method = getattr(
            self.coordinator,
            self.entity_description.write_method_name,
        )
        await write_method(
            self.entity_description.field_name,
            self.entity_description.on_value,
        )

    async def async_turn_off(self, **kwargs: object) -> None:
        """Turn off this Thermia switch."""
        write_method = getattr(
            self.coordinator,
            self.entity_description.write_method_name,
        )
        await write_method(
            self.entity_description.field_name,
            self.entity_description.off_value,
        )


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Thermia Calibra switches."""
    coordinator: ThermiaCalibraCoordinator = entry.runtime_data
    async_add_entities(
        ThermiaCalibraSwitch(coordinator, entry, description)
        for description in SWITCHES
    )
