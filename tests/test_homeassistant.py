"""Exercise the real Home Assistant number platform when Core is installed."""

from __future__ import annotations

import importlib.util
import asyncio
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

HAS_HOME_ASSISTANT = importlib.util.find_spec("homeassistant") is not None

if HAS_HOME_ASSISTANT:
    from homeassistant.components.climate import async_service_temperature_set
    from homeassistant.components.climate.const import ClimateEntityFeature, HVACAction, HVACMode
    from homeassistant.exceptions import ConfigEntryError, HomeAssistantError
    from homeassistant.util.unit_system import METRIC_SYSTEM
    from modbus_connection import IllegalDataAddressError
    from modbus_connection.mock import MockModbusConnection

    from custom_components.thermia_calibra.coordinator import ThermiaCalibraCoordinator
    from custom_components.thermia_calibra.climate import ThermiaCalibraHotWaterClimate, async_setup_entry
    from custom_components.thermia_calibra.number import NUMBERS, ThermiaCalibraNumber
    from custom_components.thermia_calibra.vendor.thermia_calibra_modbus import ThermiaCalibra
    import custom_components.thermia_calibra as integration


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


@unittest.skipUnless(HAS_HOME_ASSISTANT, "Requires Home Assistant; covered by the core-tests CI job")
class HomeAssistantHotWaterTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.connection = MockModbusConnection()
        self.unit = self.connection.for_unit(1)
        self.unit.holding.update({22: 4500, 23: 5800})
        self.unit.input.update({1: 99, 17: 5330})
        self.unit.coils[8] = True
        self.device = ThermiaCalibra(self.unit)
        self.coordinator = SimpleNamespace(
            device=self.device,
            data=await self.device.async_update_readings(),
            last_update_success=True,
            async_write_hot_water_range=AsyncMock(),
            async_write_hot_water_enabled=AsyncMock(),
            async_request_refresh=AsyncMock(),
        )
        self.entry = SimpleNamespace(entry_id="existing-entry", data={"host": "pump", "port": 502, "unit_id": 1}, runtime_data=self.coordinator)
        self.entity = ThermiaCalibraHotWaterClimate(self.coordinator, self.entry)
        self.entity.hass = SimpleNamespace(config=SimpleNamespace(units=METRIC_SYSTEM))

    async def asyncTearDown(self):
        await self.connection.close()

    async def test_opt_in_platform_setup_writes_nothing(self):
        entities = []
        await async_setup_entry(self.entity.hass, self.entry, entities.extend)
        self.assertEqual(len(entities), 1)
        self.assertFalse(entities[0].entity_registry_enabled_default)
        self.assertEqual(entities[0].unique_id, "existing-entry_hot_water")
        self.assertEqual(entities[0].device_info["identifiers"], {("thermia_calibra", "pump:502:1")})
        self.coordinator.async_write_hot_water_range.assert_not_awaited()
        self.coordinator.async_write_hot_water_enabled.assert_not_awaited()

    async def test_real_climate_state_and_capabilities(self):
        self.assertEqual((self.entity.min_temp, self.entity.max_temp, self.entity.target_temperature_step), (20, 70, 0.5))
        self.assertTrue(self.entity.available)
        self.assertEqual(self.entity.state, "auto")
        self.assertEqual(self.entity.state_attributes["target_temp_low"], 45)
        self.assertEqual(self.entity.state_attributes["target_temp_high"], 58)
        self.assertEqual(self.entity.state_attributes["current_temperature"], 53.3)
        self.assertEqual(self.entity.capability_attributes["hvac_modes"], [HVACMode.OFF, HVACMode.AUTO])
        self.assertFalse(self.entity.supported_features & ClimateEntityFeature.PRESET_MODE)

    async def test_legacy_options_cannot_enable_presets_or_a_second_controller(self):
        self.entry.options = {"controller_enabled": True}
        self.coordinator.controller_enabled = True
        self.assertFalse(self.entity.supported_features & ClimateEntityFeature.PRESET_MODE)
        self.assertEqual(self.entity.extra_state_attributes, {"automatic_control_enabled": False})
        await self.entity.async_set_temperature(target_temp_low=46, target_temp_high=59)
        self.coordinator.async_write_hot_water_range.assert_awaited_once_with(46, 59)

    async def test_real_temperature_service_routes_both_native_targets(self):
        await async_service_temperature_set(self.entity, SimpleNamespace(data={"target_temp_low": 46, "target_temp_high": 59}))
        self.coordinator.async_write_hot_water_range.assert_awaited_once_with(46, 59)
        self.coordinator.async_write_hot_water_enabled.assert_not_awaited()

    async def test_mode_reads_controller_not_local_request(self):
        await self.entity.async_set_hvac_mode(HVACMode.OFF)
        self.coordinator.async_write_hot_water_enabled.assert_awaited_once_with(False)
        self.assertEqual(self.entity.hvac_mode, HVACMode.AUTO)
        self.unit.coils[8] = False
        self.coordinator.data = await self.device.async_update_readings()
        self.assertEqual(self.entity.hvac_mode, HVACMode.OFF)

    async def test_real_turn_on_and_off_use_only_normal_tap_water_coil(self):
        await self.entity.async_turn_off()
        await self.entity.async_turn_on()
        self.assertEqual([call.args for call in self.coordinator.async_write_hot_water_enabled.await_args_list], [(False,), (True,)])
        self.coordinator.async_write_hot_water_range.assert_not_awaited()

    async def test_activity_uses_current_demand_including_anti_legionella(self):
        for code, expected in ((99, HVACAction.IDLE), (3, HVACAction.HEATING), (7, HVACAction.HEATING), (999, None)):
            self.unit.input[1] = code
            self.coordinator.data = await self.device.async_update_readings()
            self.assertEqual(self.entity.hvac_action, expected)
        self.unit.coils[8] = False
        self.unit.input[1] = 7
        self.coordinator.data = await self.device.async_update_readings()
        self.assertEqual(self.entity.hvac_mode, HVACMode.OFF)
        self.assertEqual(self.entity.hvac_action, HVACAction.HEATING)

    async def test_stale_input_does_not_show_cached_temperature_or_activity(self):
        self.unit.fail_read(1, IllegalDataAddressError(), register_type="input")
        self.coordinator.data = await self.device.async_update_readings()
        self.assertIsNone(self.entity.current_temperature)
        self.assertIsNone(self.entity.hvac_action)
        self.assertTrue(self.entity.available)

    async def test_stale_controls_make_entity_unavailable(self):
        for name in ("coils", "holding_registers"):
            data = self.coordinator.data
            self.coordinator.data = SimpleNamespace(updated=[group for group in data.updated if group != name])
            self.assertFalse(self.entity.available)
            self.coordinator.data = data

    async def test_invalid_controller_pair_is_unavailable(self):
        self.unit.holding[22] = 6000
        self.coordinator.data = await self.device.async_update_readings()
        self.assertFalse(self.entity.available)

    async def test_incomplete_or_unsupported_services_write_nothing(self):
        for kwargs in ({"temperature": 58}, {"target_temp_low": 45}, {"target_temp_low": 45, "target_temp_high": 58, "hvac_mode": HVACMode.COOL}):
            with self.assertRaises(HomeAssistantError):
                await self.entity.async_set_temperature(**kwargs)
        with self.assertRaises(HomeAssistantError):
            await self.entity.async_set_hvac_mode(HVACMode.HEAT)
        self.coordinator.async_write_hot_water_range.assert_not_awaited()
        self.coordinator.async_write_hot_water_enabled.assert_not_awaited()

    async def test_combined_request_does_not_change_mode_after_range_failure(self):
        self.coordinator.async_write_hot_water_range.side_effect = HomeAssistantError("write failed")
        with self.assertRaises(HomeAssistantError):
            await self.entity.async_set_temperature(target_temp_low=46, target_temp_high=59, hvac_mode=HVACMode.OFF)
        self.coordinator.async_write_hot_water_enabled.assert_not_awaited()

    async def test_verified_coordinator_request_refreshes(self):
        await ThermiaCalibraCoordinator.async_write_hot_water_range(self.coordinator, 46, 59)
        self.assertEqual(self.unit.holding[22], 4600)
        self.coordinator.async_request_refresh.assert_awaited_once()

    async def test_partial_failure_surfaces_error_and_refreshes_actual_values(self):
        self.unit.fail_write(23, IllegalDataAddressError())
        with self.assertRaisesRegex(HomeAssistantError, "Check both controller temperatures"):
            await ThermiaCalibraCoordinator.async_write_hot_water_range(self.coordinator, 46, 59)
        self.assertEqual((self.unit.holding[22], self.unit.holding[23]), (4600, 5800))
        self.coordinator.async_request_refresh.assert_awaited_once()

    async def test_verified_mode_coordinator_request_refreshes(self):
        await ThermiaCalibraCoordinator.async_write_hot_water_enabled(self.coordinator, False)
        self.assertFalse(self.unit.coils[8])
        self.coordinator.async_request_refresh.assert_awaited_once()

    async def test_failed_mode_coordinator_request_refreshes(self):
        self.unit.fail_write(8, IllegalDataAddressError(), register_type="coil")
        with self.assertRaises(HomeAssistantError):
            await ThermiaCalibraCoordinator.async_write_hot_water_enabled(self.coordinator, False)
        self.coordinator.async_request_refresh.assert_awaited_once()






@unittest.skipUnless(HAS_HOME_ASSISTANT, "Requires Home Assistant; covered by the core-tests CI job")
class HomeAssistantDirectCommandTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.connection = MockModbusConnection()
        self.unit = self.connection.for_unit(1)
        self.unit.holding.update({5: 2300, 22: 4500, 23: 5800, 117: 0, 118: 1230, 6257: 0})
        self.device = ThermiaCalibra(self.unit)
        self.coordinator = SimpleNamespace(
            device=self.device, _io_lock=asyncio.Lock(),
            async_request_refresh=AsyncMock(),
        )

    async def asyncTearDown(self):
        await self.connection.close()

    def requests(self):
        return (
            (ThermiaCalibraCoordinator.async_write_coil, "enable_heat", True, 9, "coil"),
            (ThermiaCalibraCoordinator.async_write_holding_register, "comfort_wheel_setting", 22, 5, "holding"),
            (ThermiaCalibraCoordinator.async_write_hot_water_register, "hot_water_boost", 1, 6257, "holding"),
        )

    async def test_every_direct_writer_refreshes_after_confirmed_command(self):
        for method, field, value, _, _ in self.requests():
            with self.subTest(field=field):
                self.coordinator.async_request_refresh.reset_mock()
                await method(self.coordinator, field, value)
                self.coordinator.async_request_refresh.assert_awaited_once_with()

    async def test_every_direct_writer_refreshes_after_rejected_command(self):
        for method, field, value, address, space in self.requests():
            with self.subTest(field=field):
                self.coordinator.async_request_refresh.reset_mock()
                self.unit.fail_write(address, IllegalDataAddressError(), register_type=space)
                with self.assertRaisesRegex(HomeAssistantError, "Check actual settings before retrying"):
                    await method(self.coordinator, field, value)
                self.coordinator.async_request_refresh.assert_awaited_once_with()
                self.unit.fail_write(address, None, register_type=space)

    async def test_every_direct_writer_refreshes_after_unconfirmed_applied_command(self):
        for method, field, value, address, space in self.requests():
            with self.subTest(field=field):
                self.coordinator.async_request_refresh.reset_mock()
                unsubscribe = self.unit.on_write(lambda _, a=address, s=space: self.unit.fail_read(a, IllegalDataAddressError(), register_type=s))
                with self.assertRaises(HomeAssistantError):
                    await method(self.coordinator, field, value)
                self.coordinator.async_request_refresh.assert_awaited_once_with()
                unsubscribe()
                self.unit.fail_read(address, None, register_type=space)


@unittest.skipUnless(HAS_HOME_ASSISTANT, "Requires Home Assistant; covered by the core-tests CI job")
class HomeAssistantDeviceOnlyTests(unittest.IsolatedAsyncioTestCase):
    async def test_polling_only_reads_device(self):
        report = SimpleNamespace(updated={"input_registers"}, failed={})
        coord = SimpleNamespace(_io_lock=asyncio.Lock(), _async_poll_device=AsyncMock(return_value=report))
        self.assertIs(await ThermiaCalibraCoordinator._async_update_data(coord), report)
        coord._async_poll_device.assert_awaited_once_with()

    async def test_unload_does_not_restore_or_change_pump_settings(self):
        hass = SimpleNamespace(config_entries=SimpleNamespace(async_unload_platforms=AsyncMock(return_value=True)))
        self.assertTrue(await integration.async_unload_entry(hass, SimpleNamespace()))

    async def test_legacy_controller_blocks_before_opening_pump_connection(self):
        store = SimpleNamespace(async_load=AsyncMock(return_value=None), async_save=AsyncMock())
        entry = SimpleNamespace(entry_id="old-entry", options={"controller_enabled": True})
        with patch.object(integration, "Store", return_value=store), patch.object(integration, "async_get_unit") as get_unit:
            with self.assertRaisesRegex(ConfigEntryError, "Return to 0.1.12b2"):
                await integration.async_setup_entry(SimpleNamespace(), entry)
            get_unit.assert_not_called()
            store.async_save.assert_not_awaited()

    async def test_fresh_setup_only_refreshes_and_registers_existing_platforms(self):
        store = SimpleNamespace(async_load=AsyncMock(return_value=None), async_save=AsyncMock())
        coordinator = SimpleNamespace(async_config_entry_first_refresh=AsyncMock())
        hass = SimpleNamespace(config_entries=SimpleNamespace(async_forward_entry_setups=AsyncMock()))
        entry = SimpleNamespace(entry_id="entry", options={}, data={"host": "pump", "port": 502, "unit_id": 1})
        with patch.object(integration, "Store", return_value=store), patch.object(integration, "async_get_unit"), patch.object(integration, "ThermiaCalibra"), patch.object(integration, "ThermiaCalibraCoordinator", return_value=coordinator):
            self.assertTrue(await integration.async_setup_entry(hass, entry))
            coordinator.async_config_entry_first_refresh.assert_awaited_once_with()
            self.assertIs(entry.runtime_data, coordinator)
            hass.config_entries.async_forward_entry_setups.assert_awaited_once()
            store.async_save.assert_not_awaited()


if __name__ == "__main__":
    unittest.main()
