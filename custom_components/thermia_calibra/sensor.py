"""Read-only Thermia Calibra sensors."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST, CONF_PORT, PERCENTAGE, UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import CONF_UNIT_ID, DEVICE_MODEL, DEVICE_NAME, DOMAIN, MANUFACTURER
from .coordinator import ThermiaCalibraCoordinator
from .vendor.thermia_calibra_modbus import ThermiaCalibra

SensorValue = str | int | float | None
UNIT_HOURS = "h"
UNIT_RPM = "rpm"


@dataclass(frozen=True, kw_only=True)
class ThermiaCalibraSensorDescription(SensorEntityDescription):
    """Describe one Thermia Calibra sensor."""

    value_fn: Callable[[ThermiaCalibra], SensorValue]
    report_name: str


SENSORS: tuple[ThermiaCalibraSensorDescription, ...] = (
    ThermiaCalibraSensorDescription(
        key="heatpump",
        name="Heatpump",
        report_name="input_registers",
        value_fn=lambda device: device.heatpump_status,
    ),
    ThermiaCalibraSensorDescription(
        key="return_line_temperature",
        name="Return Line Temperature",
        device_class=SensorDeviceClass.TEMPERATURE,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        state_class=SensorStateClass.MEASUREMENT,
        report_name="input_registers",
        value_fn=lambda device: device.input_registers.condenser_in_temperature,
    ),
    ThermiaCalibraSensorDescription(
        key="supply_line_temperature",
        name="Supply Line Temperature",
        device_class=SensorDeviceClass.TEMPERATURE,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        state_class=SensorStateClass.MEASUREMENT,
        report_name="input_registers",
        value_fn=lambda device: device.input_registers.condenser_out_temperature,
    ),
    ThermiaCalibraSensorDescription(
        key="compressor_speed_rpm",
        name="Compressor Speed RPM",
        native_unit_of_measurement=UNIT_RPM,
        state_class=SensorStateClass.MEASUREMENT,
        report_name="input_registers",
        value_fn=lambda device: device.input_registers.compressor_speed_rpm,
    ),
    ThermiaCalibraSensorDescription(
        key="condenser_in_temperature",
        name="Condenser In Temperature",
        device_class=SensorDeviceClass.TEMPERATURE,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        state_class=SensorStateClass.MEASUREMENT,
        entity_registry_enabled_default=False,
        report_name="input_registers",
        value_fn=lambda device: device.input_registers.condenser_in_temperature,
    ),
    ThermiaCalibraSensorDescription(
        key="condenser_out_temperature",
        name="Condenser Out Temperature",
        device_class=SensorDeviceClass.TEMPERATURE,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        state_class=SensorStateClass.MEASUREMENT,
        entity_registry_enabled_default=False,
        report_name="input_registers",
        value_fn=lambda device: device.input_registers.condenser_out_temperature,
    ),
    ThermiaCalibraSensorDescription(
        key="brine_in_temperature",
        name="Brine In Temperature",
        device_class=SensorDeviceClass.TEMPERATURE,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        state_class=SensorStateClass.MEASUREMENT,
        report_name="input_registers",
        value_fn=lambda device: device.input_registers.brine_in_temperature,
    ),
    ThermiaCalibraSensorDescription(
        key="brine_out_temperature",
        name="Brine Out Temperature",
        device_class=SensorDeviceClass.TEMPERATURE,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        state_class=SensorStateClass.MEASUREMENT,
        report_name="input_registers",
        value_fn=lambda device: device.input_registers.brine_out_temperature,
    ),
    ThermiaCalibraSensorDescription(
        key="system_supply_line_temperature",
        name="System Supply Line Temperature",
        device_class=SensorDeviceClass.TEMPERATURE,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        state_class=SensorStateClass.MEASUREMENT,
        entity_registry_enabled_default=False,
        report_name="input_registers",
        value_fn=lambda device: device.input_registers.system_supply_line_temperature,
    ),
    ThermiaCalibraSensorDescription(
        key="outdoor_temperature",
        name="Outdoor Temperature",
        device_class=SensorDeviceClass.TEMPERATURE,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        state_class=SensorStateClass.MEASUREMENT,
        report_name="input_registers",
        value_fn=lambda device: device.input_registers.outdoor_temperature,
    ),
    ThermiaCalibraSensorDescription(
        key="cooling_start_temperature",
        name="Cooling Start Temperature",
        device_class=SensorDeviceClass.TEMPERATURE,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        report_name="holding_registers",
        value_fn=lambda device: device.holding_registers.cooling_start_temperature,
    ),
    ThermiaCalibraSensorDescription(
        key="cooling_stop_temperature",
        name="Cooling Stop Temperature",
        device_class=SensorDeviceClass.TEMPERATURE,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        report_name="holding_registers",
        value_fn=lambda device: device.holding_registers.cooling_stop_temperature,
    ),
    ThermiaCalibraSensorDescription(
        key="heating_season_stop_temperature",
        name="Heating Season Stop Temperature",
        device_class=SensorDeviceClass.TEMPERATURE,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        report_name="holding_registers",
        value_fn=lambda device: device.holding_registers.heating_season_stop_temperature,
    ),
    ThermiaCalibraSensorDescription(
        key="cooling_minimum_outdoor_temperature_permitted",
        name="Cooling Minimum Outdoor Temperature Permitted",
        device_class=SensorDeviceClass.TEMPERATURE,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        report_name="holding_registers",
        value_fn=lambda device: (
            device.holding_registers.cooling_minimum_outdoor_temperature_permitted
        ),
    ),
    ThermiaCalibraSensorDescription(
        key="mix_valve_1_selected_mode",
        name="Mix Valve 1 Selected Mode",
        report_name="holding_registers",
        value_fn=lambda device: device.holding_registers.mix_valve_1_selected_mode,
    ),
    ThermiaCalibraSensorDescription(
        key="tap_water_top_temperature",
        name="Tap Water Top Temperature",
        device_class=SensorDeviceClass.TEMPERATURE,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        state_class=SensorStateClass.MEASUREMENT,
        report_name="input_registers",
        value_fn=lambda device: device.input_registers.tap_water_top_temperature,
    ),
    ThermiaCalibraSensorDescription(
        key="tap_water_lower_temperature",
        name="Tap Water Lower Temperature",
        device_class=SensorDeviceClass.TEMPERATURE,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        state_class=SensorStateClass.MEASUREMENT,
        report_name="input_registers",
        value_fn=lambda device: device.input_registers.tap_water_lower_temperature,
    ),
    ThermiaCalibraSensorDescription(
        key="tap_water_weighted_temperature",
        name="Tap Water Weighted Temperature",
        device_class=SensorDeviceClass.TEMPERATURE,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        state_class=SensorStateClass.MEASUREMENT,
        report_name="input_registers",
        value_fn=lambda device: device.input_registers.tap_water_weighted_temperature,
    ),
    ThermiaCalibraSensorDescription(
        key="system_supply_line_calculated_set_point",
        name="System Supply Line Calculated Set Point",
        device_class=SensorDeviceClass.TEMPERATURE,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        state_class=SensorStateClass.MEASUREMENT,
        report_name="input_registers",
        value_fn=lambda device: (
            device.input_registers.system_supply_line_calculated_set_point
        ),
    ),
    ThermiaCalibraSensorDescription(
        key="system_return_line_temperature",
        name="System Return Line Temperature",
        device_class=SensorDeviceClass.TEMPERATURE,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        state_class=SensorStateClass.MEASUREMENT,
        entity_registry_enabled_default=False,
        report_name="input_registers",
        value_fn=lambda device: device.input_registers.system_return_line_temperature,
    ),
    ThermiaCalibraSensorDescription(
        key="condenser_circulation_pump_speed",
        name="Condenser Circulation Pump Speed",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        report_name="input_registers",
        value_fn=lambda device: device.input_registers.condenser_circulation_pump_speed,
    ),
    ThermiaCalibraSensorDescription(
        key="brine_circulation_pump_speed",
        name="Brine Circulation Pump Speed",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        report_name="input_registers",
        value_fn=lambda device: device.input_registers.brine_circulation_pump_speed,
    ),
    ThermiaCalibraSensorDescription(
        key="tap_water_valve_position",
        name="Tap Water Valve Position",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        report_name="input_registers",
        value_fn=lambda device: device.input_registers.tap_water_valve_position,
    ),
    ThermiaCalibraSensorDescription(
        key="compressor_operating_hours",
        name="Compressor Operating Hours",
        native_unit_of_measurement=UNIT_HOURS,
        state_class=SensorStateClass.TOTAL_INCREASING,
        report_name="input_registers",
        value_fn=lambda device: device.input_registers.compressor_operating_hours,
    ),
    ThermiaCalibraSensorDescription(
        key="tap_water_operating_hours",
        name="Tap Water Operating Hours",
        native_unit_of_measurement=UNIT_HOURS,
        state_class=SensorStateClass.TOTAL_INCREASING,
        report_name="input_registers",
        value_fn=lambda device: device.input_registers.tap_water_operating_hours,
    ),
    ThermiaCalibraSensorDescription(
        key="external_additional_heater_operating_hours",
        name="External Additional Heater Operating Hours",
        native_unit_of_measurement=UNIT_HOURS,
        state_class=SensorStateClass.TOTAL_INCREASING,
        report_name="input_registers",
        value_fn=lambda device: (
            device.input_registers.external_additional_heater_operating_hours
        ),
    ),
    ThermiaCalibraSensorDescription(
        key="compressor_speed_percent",
        name="Compressor Speed Percent",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        report_name="input_registers",
        value_fn=lambda device: device.input_registers.compressor_speed_percent,
    ),
    ThermiaCalibraSensorDescription(
        key="compressor_current_gear",
        name="Compressor Current Gear",
        state_class=SensorStateClass.MEASUREMENT,
        report_name="input_registers",
        value_fn=lambda device: device.input_registers.compressor_current_gear,
    ),
    ThermiaCalibraSensorDescription(
        key="mix_valve_cooling_opening_degree",
        name="Mix Valve Cooling Opening Degree",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        report_name="input_registers",
        value_fn=lambda device: device.input_registers.mix_valve_cooling_opening_degree,
    ),
    ThermiaCalibraSensorDescription(
        key="active_alarms",
        name="Active Alarms",
        state_class=SensorStateClass.MEASUREMENT,
        report_name="discrete_inputs",
        value_fn=lambda device: device.active_alarms,
    ),
)


class ThermiaCalibraSensor(CoordinatorEntity[ThermiaCalibraCoordinator], SensorEntity):
    """Thermia Calibra read-only sensor."""

    entity_description: ThermiaCalibraSensorDescription
    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: ThermiaCalibraCoordinator,
        entry: ConfigEntry,
        description: ThermiaCalibraSensorDescription,
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
    def native_value(self) -> SensorValue:
        """Return the sensor value."""
        return self.entity_description.value_fn(self.coordinator.device)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Thermia Calibra sensors."""
    coordinator: ThermiaCalibraCoordinator = entry.runtime_data
    async_add_entities(
        ThermiaCalibraSensor(coordinator, entry, description)
        for description in SENSORS
    )
