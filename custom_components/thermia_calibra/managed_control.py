"""Opt-in policy bridge with durable write ownership and a narrow register set."""

from __future__ import annotations

import math
from copy import deepcopy
from typing import Any

from .vendor.genesis_policy.control import ControlEngine
from .vendor.genesis_policy.device import ThermiaDevice
from .vendor.genesis_policy.native_settings import NATIVE_SETTINGS

DEFAULT_CONTROL_OPTIONS = {
    "controller_enabled": False,
    "confirm_other_controllers_disabled": False,
    "confirm_native_boost": False,
    "inside_sensor": "",
    "inside_humidity_sensor": "",
    "sensor_timeout": 900,
    "hysteresis": 0.3,
    "heating_low_offset": 2.0,
    "heating_vacation_temperature": 17.0,
    "heating_vacation_cooling_offset": 0.0,
    "max_heating_temperature": 23.0,
    "charge_supply_temperature": 35.0,
    "heating_excess_hours": 12.0,
    "heating_excess_heat_stop_offset": 2.0,
    "hot_water_excess_hours": 6.0,
    "hot_water_low_hours": 24.0,
    "hot_water_evening_start": 35.0,
    "hot_water_evening_stop": 40.0,
    "hot_water_hysteresis": 3.0,
    "max_start_temperature": 60.0,
    "max_hot_water_temperature": 60.0,
    "cooling_humidity_enabled": False,
    "cooling_humidity_limit": 80.0,
    "cooling_vacation_humidity_limit": 65.0,
    "cooling_dew_point_margin": 2.0,
}

CONTROL_KEYS = frozenset({
    "heating_enabled", "passive_cooling_enabled", "hot_water_enabled",
    "comfort_wheel", "hot_water_start", "hot_water_stop", "hot_water_boost",
    "fixed_supply_enabled", "fixed_supply_target", "indoor_temperature",
    "room_sensor_alarm", "outdoor_temperature", "main_demand",
    "hot_water_weighted_temperature", "hot_water_top_temperature",
    "hot_water_lower_temperature",
    *NATIVE_SETTINGS,
})
WRITE_KEYS = frozenset({
    "heating_enabled", "passive_cooling_enabled", "hot_water_enabled",
    "comfort_wheel", "hot_water_start", "hot_water_stop", "hot_water_boost",
    "fixed_supply_enabled", "fixed_supply_target", "heating_season_stop",
    "passive_cooling_supply_target",
})
COMMANDS = frozenset({
    "heating_mode", "heating_preset", "heating_temperature_edit",
    "hot_water_mode", "hot_water_temperature_edit",
})


def control_options(options: dict) -> dict:
    result = DEFAULT_CONTROL_OPTIONS | options
    # The imported engine contains other APIs; they are deliberately not exposed.
    result.update(smart_grid_mode="disabled", enable_undocumented_controls=False)
    for key in ("controller_enabled", "confirm_other_controllers_disabled", "confirm_native_boost", "cooling_humidity_enabled"):
        if not isinstance(result[key], bool):
            raise ValueError(f"{key} must be a boolean")
    for key in ("inside_sensor", "inside_humidity_sensor"):
        if not isinstance(result[key], str):
            raise ValueError(f"{key} must be an entity ID or empty")
    timeout = result["sensor_timeout"]
    if isinstance(timeout, bool) or not isinstance(timeout, (int, float)) or not 60 <= timeout <= 86400:
        raise ValueError("Sensor timeout must be between 60 and 86400 seconds")
    if result["controller_enabled"] and not result["confirm_other_controllers_disabled"]:
        raise ValueError("Confirm that other heating and hot-water controllers are disabled")
    for key in ("max_start_temperature", "max_hot_water_temperature"):
        value = result[key]
        if isinstance(value, bool) or not isinstance(value, (int, float)) or value != 60:
            raise ValueError("This beta uses the source engine's fixed 60 C Boost ceiling")
    start, stop = result["hot_water_evening_start"], result["hot_water_evening_stop"]
    if any(isinstance(value, bool) or not isinstance(value, (int, float)) for value in (start, stop)) or not 30 <= start < stop <= 60:
        raise ValueError("Low Mode needs a valid start/stop pair below the 60 C ceiling")
    validator = ControlEngine(lambda key: None, None, None, result)
    for key, value in DEFAULT_CONTROL_OPTIONS.items():
        if isinstance(value, (int, float)) and not isinstance(value, bool) and key != "sensor_timeout":
            validator._validate_setting(key, result[key])
    return result


def same_value(left: Any, right: Any) -> bool:
    if left is None or right is None:
        return left is right
    try:
        return math.isclose(float(left), float(right), abs_tol=0.005, rel_tol=0)
    except (TypeError, ValueError):
        return False


class ManagedControl:
    """Serialize externally and refuse to overwrite changes by another controller."""

    def __init__(self, unit, options, persist, saved=None, **engine_kwargs):
        self.options = control_options(options)
        self.enabled = self.options["controller_enabled"]
        self.adapter = ThermiaDevice(unit, undocumented=self.options["confirm_native_boost"])
        self.adapter.specs = {
            key: spec for key, spec in self.adapter.specs.items() if key in CONTROL_KEYS
        }
        self._persist = persist
        saved = saved or {}
        self.ownership = deepcopy(saved.get("ownership", {}))
        self.blocked = saved.get("blocked")
        self.ready = False
        self.recover_pending = bool(saved.get("control"))
        self.engine = ControlEngine(
            self.value, self._write, self._save, self.options,
            saved.get("control"), **engine_kwargs,
        )

    def value(self, key):
        return self.adapter.values.get(key) if self.ready else None

    async def _save(self, state):
        await self._persist({
            "control": deepcopy(state), "ownership": deepcopy(self.ownership),
            "blocked": self.blocked,
        })

    async def _block(self, message):
        self.blocked = message
        await self._save(self.engine.state)
        raise ValueError(message)

    async def _check_ownership(self):
        if self.blocked:
            raise ValueError(self.blocked)
        for key, record in self.ownership.items():
            actual = self.value(key)
            if actual is None:
                raise ValueError(f"Cannot verify ownership of {key}; controller readback unavailable")
            if same_value(actual, record["after"]):
                record["confirmed"] = True
            elif not record["confirmed"] and same_value(actual, record["before"]):
                continue
            else:
                await self._block(
                    f"{key} changed outside this thermostat. Automatic control is suspended; "
                    "inspect the pump and release control explicitly before resuming."
                )

    async def _write(self, key, value):
        if not self.enabled or not self.ready or self.blocked:
            raise ValueError(self.blocked or "Automatic thermostat control is not enabled or ready")
        if key not in WRITE_KEYS:
            raise ValueError(f"The Calibra thermostat does not own {key}")
        if key == "hot_water_boost" and not self.options["confirm_native_boost"]:
            raise ValueError("Native Boost must be physically verified and explicitly enabled")
        cached = self.value(key)
        current = await self.adapter.async_read_value(key)
        if current is None:
            raise ValueError(f"No current controller readback for {key}")
        if key in self.ownership:
            record = self.ownership[key]
            allowed = [record["after"]] + ([] if record["confirmed"] else [record["before"]])
            if not any(same_value(current, expected) for expected in allowed):
                await self._block(f"External change to {key}; automatic control suspended")
        elif not same_value(current, cached):
            await self._block(f"{key} changed during this request; automatic control suspended")
        if same_value(current, value):
            return
        if key in {"hot_water_start", "hot_water_stop"}:
            other = "hot_water_stop" if key == "hot_water_start" else "hot_water_start"
            other_value = await self.adapter.async_read_value(other)
            start, stop = (value, other_value) if key == "hot_water_start" else (other_value, value)
            boost = self.engine.state.get("hot_water_mode") == "energy_excess" or bool(
                self.engine.state["overrides"].get("hot_water")
            )
            if start is None or stop is None or start > stop or (
                start == stop and not (start == 60 and boost and self.options["confirm_native_boost"])
            ):
                raise ValueError("Invalid intermediate hot-water temperatures")
        # Persist intent before I/O: lost replies and crashes cannot erase ownership.
        self.ownership[key] = {"before": current, "after": value, "confirmed": False}
        await self._save(self.engine.state)
        await self.adapter.async_write(key, value)
        self.ownership[key]["confirmed"] = True
        await self._save(self.engine.state)

    async def update(self, inside=None, outdoor=None, humidity=None):
        if not self.enabled:
            return
        self.ready = False
        await self.adapter.async_update()
        self.ready = True
        await self._check_ownership()
        inside = inside() if callable(inside) else inside
        outdoor = outdoor() if callable(outdoor) else outdoor
        humidity = humidity() if callable(humidity) else humidity
        self.engine.update_measurements(inside, outdoor, humidity)
        if self.recover_pending:
            if not await self.engine.recover():
                raise ValueError("Thermostat restoration is pending")
            self.recover_pending = False
        await self.engine.tick(inside, outdoor, humidity)

    async def command(self, action, value, inside=None, outdoor=None, humidity=None):
        if not self.enabled:
            raise ValueError("Enable thermostat control in the integration options first")
        if action not in COMMANDS:
            raise ValueError("Unsupported thermostat command")
        # No commands run on a stale poll or ahead of pending restoration.
        await self.update(inside, outdoor, humidity)
        await self.engine.command(action, value)

    async def shutdown(self):
        if not self.enabled:
            return
        self.ready = False
        await self.adapter.async_update()
        self.ready = True
        await self._check_ownership()
        if not await self.engine.shutdown():
            raise ValueError("Restore the pump settings before disabling thermostat control")
        self.ownership.clear()
        await self._save(self.engine.state)

    async def release_after_external_change(self):
        """Explicitly abandon the journal without touching externally changed hardware."""
        if not self.blocked:
            raise ValueError("Control is not suspended by an external change")
        self.ownership.clear()
        self.blocked = None
        self.recover_pending = False
        self.engine = ControlEngine(self.value, self._write, self._save, self.options)
        await self._save(self.engine.state)
