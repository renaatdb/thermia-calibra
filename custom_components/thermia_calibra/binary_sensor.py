"""Read-only Thermia Calibra binary sensors."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
    BinarySensorEntityDescription,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST, CONF_PORT
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import CONF_UNIT_ID, DEVICE_MODEL, DEVICE_NAME, DOMAIN, MANUFACTURER
from .coordinator import ThermiaCalibraCoordinator
from .vendor.thermia_calibra_modbus import ThermiaCalibra


@dataclass(frozen=True, kw_only=True)
class ThermiaCalibraBinarySensorDescription(BinarySensorEntityDescription):
    """Describe one Thermia Calibra binary sensor."""

    value_fn: Callable[[ThermiaCalibra], bool | None]
    report_name: str


BINARY_SENSORS: tuple[ThermiaCalibraBinarySensorDescription, ...] = (
    ThermiaCalibraBinarySensorDescription(
        key="hot_water_operational_status",
        name="Hot Water Operational Status",
        report_name="input_registers",
        value_fn=lambda device: device.hot_water_operational,
    ),
    ThermiaCalibraBinarySensorDescription(
        key="anti_legionella_operational_status",
        name="Anti Legionella Operational Status",
        report_name="input_registers",
        value_fn=lambda device: device.anti_legionella_operational,
    ),
    ThermiaCalibraBinarySensorDescription(
        key="passive_cooling_active",
        name="Passive Cooling Active",
        report_name="input_registers",
        value_fn=lambda device: device.passive_cooling_active,
    ),
    ThermiaCalibraBinarySensorDescription(
        key="maximum_time_for_anti_legionella_exceeded",
        name="Maximum Time For Anti Legionella Exceeded",
        device_class=BinarySensorDeviceClass.PROBLEM,
        report_name="discrete_inputs",
        value_fn=lambda device: (
            device.discrete_inputs.maximum_time_for_anti_legionella_exceeded
        ),
    ),
)


class ThermiaCalibraBinarySensor(
    CoordinatorEntity[ThermiaCalibraCoordinator],
    BinarySensorEntity,
):
    """Thermia Calibra read-only binary sensor."""

    entity_description: ThermiaCalibraBinarySensorDescription
    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: ThermiaCalibraCoordinator,
        entry: ConfigEntry,
        description: ThermiaCalibraBinarySensorDescription,
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
        """Return the binary sensor state."""
        return self.entity_description.value_fn(self.coordinator.device)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Thermia Calibra binary sensors."""
    coordinator: ThermiaCalibraCoordinator = entry.runtime_data
    async_add_entities(
        ThermiaCalibraBinarySensor(coordinator, entry, description)
        for description in BINARY_SENSORS
    )
