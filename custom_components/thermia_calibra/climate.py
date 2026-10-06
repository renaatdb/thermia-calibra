"""Opt-in native hot-water view and managed heating/cooling thermostats."""

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
from homeassistant.const import (
    ATTR_TEMPERATURE, CONF_HOST, CONF_PORT, UnitOfTemperature
)
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import CONF_UNIT_ID, DEVICE_MODEL, DEVICE_NAME, DOMAIN, MANUFACTURER
from .coordinator import ThermiaCalibraCoordinator
from .vendor.genesis_policy.excess_time import excess_time_attributes, low_time_attributes
from .vendor.thermia_calibra_modbus.hot_water import (
    START_MIN,
    STOP_MAX,
    TEMPERATURE_STEP,
    validate_hot_water_range,
)


class ThermiaCalibraHotWaterClimate(
    CoordinatorEntity[ThermiaCalibraCoordinator], ClimateEntity
):
    """Keep the native view unless the optional profile controller is enabled."""

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
        return (
            self.coordinator.data is not None
            and name in self.coordinator.data.updated
        )

    @property
    def _managed(self) -> bool:
        return getattr(self.coordinator, "controller_enabled", False)

    @property
    def supported_features(self):
        features = self._attr_supported_features
        return features | ClimateEntityFeature.PRESET_MODE if self._managed else features

    @property
    def preset_modes(self):
        return ["Normal", "Excess Energy", "Low Mode"] if self._managed and self.hvac_mode != HVACMode.OFF else []

    @property
    def preset_mode(self):
        if not self._managed or self.hvac_mode == HVACMode.OFF:
            return None
        return {"energy_excess": "Excess Energy", "evening": "Low Mode"}.get(
            self.coordinator.engine.state["hot_water_mode"], "Normal"
        )

    @property
    def extra_state_attributes(self):
        if not self._managed:
            return {"automatic_control_enabled": False}
        return {
            "automatic_control_enabled": True,
            "control_warning": self.coordinator.control_error or self.coordinator.engine.state["control_warning"],
            "native_boost_physically_confirmed": self.coordinator.control.options["confirm_native_boost"],
            **excess_time_attributes(self.coordinator, "hot_water"),
            **low_time_attributes(self.coordinator),
        }

    async def async_set_preset_mode(self, preset_mode):
        modes = {"Normal": "auto", "Excess Energy": "energy_excess", "Low Mode": "evening"}
        if not self._managed or self.hvac_mode == HVACMode.OFF or preset_mode not in modes:
            raise HomeAssistantError("Enable thermostat control and tap water before selecting a preset")
        await self.coordinator.async_control_command("hot_water_mode", modes[preset_mode])

    @property
    def available(self) -> bool:
        if self._managed:
            if self.coordinator.control_error or not self.coordinator.control.ready:
                return False
            start, stop = self.target_temperature_low, self.target_temperature_high
            if start == stop == 60 and self.coordinator.control.options["confirm_native_boost"]:
                return super().available
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
            and self.target_temperature_low is not None
            and self.target_temperature_high is not None
        )

    @property
    def hvac_mode(self) -> HVACMode | None:
        if self._managed:
            return HVACMode.OFF if self.coordinator.engine.state["hot_water_mode"] == "off" else HVACMode.AUTO
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
        if self._managed:
            return self.coordinator.control.value("hot_water_start")
        if not self._group_updated("holding_registers"):
            return None
        return self.coordinator.device.holding_registers.start_temperature_tap_water

    @property
    def target_temperature_high(self) -> float | None:
        if self._managed:
            return self.coordinator.control.value("hot_water_stop")
        if not self._group_updated("holding_registers"):
            return None
        return self.coordinator.device.holding_registers.stop_temperature_tap_water

    async def async_set_hvac_mode(self, hvac_mode: HVACMode) -> None:
        if hvac_mode not in self.hvac_modes:
            raise HomeAssistantError("Hot water supports only auto and off")
        if self._managed:
            await self.coordinator.async_control_command(
                "hot_water_mode", "auto" if hvac_mode == HVACMode.AUTO else "off"
            )
        else:
            await self.coordinator.async_write_hot_water_enabled(hvac_mode == HVACMode.AUTO)

    async def async_set_temperature(self, **kwargs: Any) -> None:
        if ATTR_TEMPERATURE in kwargs or any(
            key not in kwargs for key in (ATTR_TARGET_TEMP_LOW, ATTR_TARGET_TEMP_HIGH)
        ):
            raise HomeAssistantError("Supply both hot-water start and stop temperatures")
        mode = kwargs.get(ATTR_HVAC_MODE)
        if mode is not None and mode not in self.hvac_modes:
            raise HomeAssistantError("Hot water supports only auto and off")
        if self._managed:
            await self.coordinator.async_control_command("hot_water_temperature_edit", kwargs)
            return
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
    """Register an opt-in view without writing any controller settings."""
    async_add_entities([ThermiaCalibraHotWaterClimate(entry.runtime_data, entry)])
    async_add_entities([ThermiaCalibraRoomClimate(entry.runtime_data, entry)])


class ThermiaCalibraRoomClimate(ThermiaCalibraHotWaterClimate):
    """Opt-in room thermostat backed by the imported native-control policy."""

    _attr_translation_key = "heating_cooling"
    _attr_icon = "mdi:home-thermometer"
    _attr_hvac_modes = [HVACMode.OFF, HVACMode.HEAT, HVACMode.COOL, HVACMode.HEAT_COOL]
    _attr_min_temp = 10
    _attr_max_temp = 35
    _attr_target_temperature_step = 1

    def __init__(self, coordinator, entry):
        super().__init__(coordinator, entry)
        self._attr_unique_id = f"{entry.entry_id}_heating_cooling"

    @property
    def available(self):
        return (
            CoordinatorEntity.available.fget(self)
            and self._managed
            and self.coordinator.control.ready
            and not self.coordinator.control_error
            and self.coordinator.control.value("comfort_wheel") is not None
            and all(self.coordinator.control.value(key) in (False, True) for key in (
                "heating_enabled", "passive_cooling_enabled"
            ))
        )

    @property
    def supported_features(self):
        features = ClimateEntityFeature.TURN_ON | ClimateEntityFeature.TURN_OFF
        features |= (
            ClimateEntityFeature.TARGET_TEMPERATURE_RANGE
            if self.hvac_mode == HVACMode.HEAT_COOL
            else ClimateEntityFeature.TARGET_TEMPERATURE
        )
        if self.hvac_mode != HVACMode.OFF:
            features |= ClimateEntityFeature.PRESET_MODE
        return features

    @property
    def hvac_mode(self):
        return HVACMode(self.coordinator.engine.state["heating_mode"]) if self._managed else HVACMode.OFF

    @property
    def current_temperature(self):
        return getattr(self.coordinator, "effective_inside", None)

    @property
    def current_humidity(self):
        return getattr(self.coordinator, "effective_inside_humidity", None)

    @property
    def target_temperature(self):
        if not self._managed or self.hvac_mode in (HVACMode.OFF, HVACMode.HEAT_COOL):
            return None
        return self.coordinator.engine.effective_heating_target()

    @property
    def target_temperature_low(self):
        if self._managed and self.hvac_mode == HVACMode.HEAT_COOL:
            return self.coordinator.engine.effective_heating_range()[0]
        return None

    @property
    def target_temperature_high(self):
        if self._managed and self.hvac_mode == HVACMode.HEAT_COOL:
            return self.coordinator.engine.effective_heating_range()[1]
        return None

    @property
    def hvac_action(self):
        if not self._group_updated("input_registers"):
            return None
        status = self.coordinator.device.input_registers.first_prioritised_demand
        if status == 4:
            return HVACAction.HEATING
        if status in (5, 8):
            return HVACAction.COOLING
        if status not in self.coordinator.device.HEATPUMP_STATUS_BY_CODE:
            return None
        return HVACAction.OFF if self.hvac_mode == HVACMode.OFF else HVACAction.IDLE

    @property
    def preset_modes(self):
        if not self._managed or self.hvac_mode == HVACMode.OFF:
            return []
        if self.hvac_mode == HVACMode.COOL:
            return ["Normal", "Vacation"]
        if self.hvac_mode == HVACMode.HEAT_COOL:
            return ["Normal", "Excess Energy (Heating Only)", "Low Mode (Heating Only)", "Vacation"]
        return ["Normal", "Excess Energy", "Low Mode", "Vacation"]

    @property
    def preset_mode(self):
        if not self.preset_modes:
            return None
        suffix = " (Heating Only)" if self.hvac_mode == HVACMode.HEAT_COOL else ""
        return {
            "pv_charge": "Excess Energy" + suffix,
            "low": "Low Mode" + suffix,
            "vacation": "Vacation",
        }.get(self.coordinator.engine.state["heating_preset"], "Normal")

    @property
    def extra_state_attributes(self):
        if not self._managed:
            return {"automatic_control_enabled": False}
        return {
            "automatic_control_enabled": True,
            "control_warning": self.coordinator.control_error or self.coordinator.engine.state["control_warning"],
            "normal_target_temperature": self.coordinator.engine.state["heating_target"],
            "cooling_room_target_scope": "Home Assistant control; not a native cooling room setpoint",
            "native_heating_target_temperature": self.coordinator.control.value("comfort_wheel"),
            "cooling_humidity_protection": self.coordinator.engine.cooling_humidity_info(
                inside=self.current_temperature, humidity=self.current_humidity
            ),
            **excess_time_attributes(self.coordinator, "heating"),
        }

    async def async_set_hvac_mode(self, hvac_mode):
        if hvac_mode not in self.hvac_modes:
            raise HomeAssistantError("Unsupported heating/cooling mode")
        await self.coordinator.async_control_command("heating_mode", hvac_mode.value)

    async def async_set_temperature(self, **kwargs):
        await self.coordinator.async_control_command("heating_temperature_edit", kwargs)

    async def async_set_preset_mode(self, preset_mode):
        if preset_mode not in self.preset_modes:
            raise HomeAssistantError("Select an available heating/cooling preset")
        modes = {
            "Normal": "normal", "Excess Energy": "pv_charge",
            "Excess Energy (Heating Only)": "pv_charge", "Low Mode": "low",
            "Low Mode (Heating Only)": "low", "Vacation": "vacation",
        }
        await self.coordinator.async_control_command("heating_preset", modes[preset_mode])

    async def async_turn_on(self):
        await self.async_set_hvac_mode(HVACMode.HEAT)
