"""Optional direct view of the pump's native hot-water controls."""

from __future__ import annotations

import math
from typing import Any, ClassVar

from homeassistant.components.climate import ClimateEntity
from homeassistant.components.climate.const import (
    ATTR_HVAC_MODE,
    ATTR_TARGET_TEMP_HIGH,
    ATTR_TARGET_TEMP_LOW,
    ClimateEntityFeature,
    HVACAction,
    HVACMode,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import ATTR_TEMPERATURE, CONF_HOST, CONF_PORT, UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import CONF_UNIT_ID, DEVICE_MODEL, DEVICE_NAME, DOMAIN, MANUFACTURER
from .coordinator import ThermiaCalibraCoordinator
from .vendor.thermia_calibra_modbus.hot_water import (
    START_MIN,
    STOP_MAX,
    TEMPERATURE_STEP,
    validate_hot_water_range,
)


class ThermiaCalibraHotWaterClimate(
    CoordinatorEntity[ThermiaCalibraCoordinator], ClimateEntity
):
    """Expose native settings without running an additional thermostat policy."""

    _attr_has_entity_name = True
    _attr_translation_key = "hot_water"
    _attr_entity_registry_enabled_default = False
    _attr_icon = "mdi:water-thermometer"
    _attr_temperature_unit = UnitOfTemperature.CELSIUS
    _attr_hvac_modes: ClassVar[list[HVACMode]] = [HVACMode.OFF, HVACMode.AUTO]
    _attr_min_temp = START_MIN
    _attr_max_temp = STOP_MAX
    _attr_target_temperature_step = TEMPERATURE_STEP
    _attr_precision = 0.1
    _attr_supported_features = (
        ClimateEntityFeature.TARGET_TEMPERATURE_RANGE
        | ClimateEntityFeature.TURN_ON
        | ClimateEntityFeature.TURN_OFF
    )

    def __init__(
        self, coordinator: ThermiaCalibraCoordinator, entry: ConfigEntry
    ) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{entry.entry_id}_hot_water"
        self._attr_device_info = DeviceInfo(
            identifiers={
                (
                    DOMAIN,
                    f"{entry.data[CONF_HOST]}:{entry.data[CONF_PORT]}:{entry.data[CONF_UNIT_ID]}",
                )
            },
            manufacturer=MANUFACTURER,
            model=DEVICE_MODEL,
            name=DEVICE_NAME,
        )

    def _group_updated(self, name: str) -> bool:
        return self.coordinator.data is not None and name in self.coordinator.data.updated

    @property
    def extra_state_attributes(self) -> dict[str, bool]:
        return {"automatic_control_enabled": False}

    @property
    def available(self) -> bool:
        try:
            validate_hot_water_range(
                self.target_temperature_low,
                self.target_temperature_high,
                check_step=False,
            )
        except ValueError:
            return False
        return (
            super().available
            and self._group_updated("holding_registers")
            and self._group_updated("coils")
            and self.hvac_mode is not None
        )

    @property
    def hvac_mode(self) -> HVACMode | None:
        if not self._group_updated("coils"):
            return None
        enabled = self.coordinator.device.coils.enable_tap_water
        if enabled is None:
            return None
        return HVACMode.AUTO if enabled else HVACMode.OFF

    @property
    def hvac_action(self) -> HVACAction | None:
        if self.hvac_mode is None or not self._group_updated("input_registers"):
            return None
        status = self.coordinator.device.input_registers.first_prioritised_demand
        if status in (3, 7):
            return HVACAction.HEATING
        if self.hvac_mode == HVACMode.OFF:
            return HVACAction.OFF
        if status not in self.coordinator.device.HEATPUMP_STATUS_BY_CODE:
            return None
        return HVACAction.IDLE

    @property
    def current_temperature(self) -> float | None:
        if not self._group_updated("input_registers"):
            return None
        value = self.coordinator.device.input_registers.tap_water_weighted_temperature
        return value if value is not None and math.isfinite(value) else None

    @property
    def target_temperature_low(self) -> float | None:
        if not self._group_updated("holding_registers"):
            return None
        return self.coordinator.device.holding_registers.start_temperature_tap_water

    @property
    def target_temperature_high(self) -> float | None:
        if not self._group_updated("holding_registers"):
            return None
        return self.coordinator.device.holding_registers.stop_temperature_tap_water

    async def async_set_hvac_mode(self, hvac_mode: HVACMode) -> None:
        if hvac_mode not in self.hvac_modes:
            raise HomeAssistantError("Hot water supports only auto and off")
        await self.coordinator.async_write_hot_water_enabled(hvac_mode == HVACMode.AUTO)

    async def async_set_temperature(self, **kwargs: Any) -> None:
        if ATTR_TEMPERATURE in kwargs or any(
            key not in kwargs for key in (ATTR_TARGET_TEMP_LOW, ATTR_TARGET_TEMP_HIGH)
        ):
            raise HomeAssistantError("Supply both hot-water start and stop temperatures")
        mode = kwargs.get(ATTR_HVAC_MODE)
        if mode is not None and mode not in self.hvac_modes:
            raise HomeAssistantError("Hot water supports only auto and off")
        await self.coordinator.async_write_hot_water_range(
            kwargs[ATTR_TARGET_TEMP_LOW], kwargs[ATTR_TARGET_TEMP_HIGH]
        )
        if mode is not None:
            await self.async_set_hvac_mode(mode)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Register the native view without writing any pump settings."""
    async_add_entities([ThermiaCalibraHotWaterClimate(entry.runtime_data, entry)])
