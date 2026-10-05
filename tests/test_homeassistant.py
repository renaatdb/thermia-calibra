"""Exercise the real Home Assistant number platform when Core is installed."""

from __future__ import annotations

import importlib.util
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock

HAS_HOME_ASSISTANT = importlib.util.find_spec("homeassistant") is not None

if HAS_HOME_ASSISTANT:
    from homeassistant.exceptions import HomeAssistantError
    from modbus_connection import IllegalDataAddressError
    from modbus_connection.mock import MockModbusConnection

    from custom_components.thermia_calibra.coordinator import ThermiaCalibraCoordinator
    from custom_components.thermia_calibra.number import NUMBERS, ThermiaCalibraNumber
    from custom_components.thermia_calibra.vendor.thermia_calibra_modbus import ThermiaCalibra


@unittest.skipUnless(HAS_HOME_ASSISTANT, "Requires Home Assistant; covered by the core-tests CI job")
class HomeAssistantNumberTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.connection = MockModbusConnection()
        self.unit = self.connection.for_unit(1)
        self.unit.holding.update({3: 4500, 4: 2000, 5: 2100, 16: 1800, 302: 1800})
        self.unit.holding.update({6 + i: 2500 + i * 100 for i in range(7)})
        self.unit.input.update({20 + i: (2000 - i * 1000) & 0xFFFF for i in range(7)})
        self.device = ThermiaCalibra(self.unit)
        self.coordinator = SimpleNamespace(
            device=self.device,
            data=await self.device.async_update_readings(),
            last_update_success=True,
            async_write_holding_register=AsyncMock(),
            async_write_native_setting=AsyncMock(),
            async_request_refresh=AsyncMock(),
        )
        self.entry = SimpleNamespace(entry_id="existing-entry", data={"host": "pump", "port": 502, "unit_id": 1})
        self.entities = {
            description.key: ThermiaCalibraNumber(self.coordinator, self.entry, description)
            for description in NUMBERS
        }

    async def asyncTearDown(self):
        await self.connection.close()

    async def test_all_controls_construct_with_real_homeassistant_descriptions(self):
        self.assertEqual(len(self.entities), 15)
        for key, entity in self.entities.items():
            self.assertEqual(entity.unique_id, f"existing-entry_{key}")
            self.assertEqual(entity.device_info["identifiers"], {("thermia_calibra", "pump:502:1")})
            if entity.entity_description.native_setting:
                self.assertFalse(entity.entity_description.entity_registry_enabled_default)
                self.assertTrue(entity.available)

    async def test_new_controls_route_to_verified_writer(self):
        await self.entities["passive_cooling_supply_target"].async_set_native_value(20)
        self.coordinator.async_write_native_setting.assert_awaited_once_with("passive_cooling_supply_target", 20)
        self.coordinator.async_write_holding_register.assert_not_awaited()

    async def test_existing_controls_keep_their_writer_and_identity(self):
        await self.entities["comfort_wheel_setting"].async_set_native_value(21.5)
        self.coordinator.async_write_holding_register.assert_awaited_once_with("comfort_wheel_setting", 21.5)
        self.coordinator.async_write_native_setting.assert_not_awaited()
        self.assertEqual(self.entities["comfort_wheel_setting"].unique_id, "existing-entry_comfort_wheel_setting")

    async def test_missing_native_value_is_unavailable(self):
        self.unit.holding[302] = 0x4E20
        self.coordinator.data = await self.device.async_update_readings()
        self.assertIsNone(self.entities["passive_cooling_supply_target"].native_value)
        self.assertFalse(self.entities["passive_cooling_supply_target"].available)

    async def test_failed_group_is_unavailable_even_with_cached_value(self):
        self.unit.fail_read(302, IllegalDataAddressError())
        self.coordinator.data = await self.device.async_update_readings()
        self.assertFalse(self.entities["passive_cooling_supply_target"].available)
        self.assertTrue(self.entities["min_supply_temperature"].available)

    async def test_curve_attribute_uses_current_outdoor_readback(self):
        curve = self.entities["heat_curve_supply_1"]
        self.assertEqual(curve.extra_state_attributes, {"holding_register_address": 6, "outdoor_temperature": 20})
        self.unit.fail_read(20, IllegalDataAddressError(), register_type="input")
        self.coordinator.data = await self.device.async_update_readings()
        self.assertIsNone(curve.extra_state_attributes["outdoor_temperature"])
        self.assertTrue(curve.available)

    async def test_verified_coordinator_write_refreshes_state(self):
        await ThermiaCalibraCoordinator.async_write_native_setting(self.coordinator, "passive_cooling_supply_target", 20)
        self.assertEqual(self.unit.holding[302], 2000)
        self.coordinator.async_request_refresh.assert_awaited_once()

    async def test_failed_coordinator_write_reports_error_and_refreshes_state(self):
        with self.assertRaises(HomeAssistantError):
            await ThermiaCalibraCoordinator.async_write_native_setting(self.coordinator, "passive_cooling_supply_target", 31)
        self.coordinator.async_request_refresh.assert_awaited_once()


if __name__ == "__main__":
    unittest.main()
