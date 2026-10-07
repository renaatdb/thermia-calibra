"""Exercise register decoding and writes with the real Modbus model library."""

from __future__ import annotations

import asyncio
import sys
import unittest
from pathlib import Path

sys.path.insert(
    0,
    str(Path(__file__).resolve().parents[1] / "custom_components/thermia_calibra/vendor"),
)

from modbus_connection import IllegalDataAddressError, ModbusTimeoutError
from modbus_connection.mock import MockModbusConnection

from thermia_calibra_modbus import REGISTER_CATALOG, ThermiaCalibra
from thermia_calibra_modbus.native_settings import NATIVE_SETTINGS, validate_native_setting


class NativeSettingValidationTests(unittest.TestCase):
    def test_boundaries_and_steps(self):
        for key, spec in NATIVE_SETTINGS.items():
            with self.subTest(key=key):
                self.assertEqual(validate_native_setting(key, spec.min_value), spec.min_value)
                self.assertEqual(validate_native_setting(key, spec.max_value), spec.max_value)
                for value in (spec.min_value - 1, spec.max_value + 1, spec.min_value + 0.5):
                    with self.assertRaises(ValueError):
                        validate_native_setting(key, value)

    def test_invalid_types_and_nonfinite_values(self):
        for value in (True, False, "20", None, float("nan"), float("inf"), -float("inf")):
            with self.subTest(value=value), self.assertRaises(ValueError):
                validate_native_setting("heating_season_stop_temperature", value)
        with self.assertRaises(ValueError):
            validate_native_setting("enable_heat", 20)

    def test_catalog_has_no_duplicate_keys_or_addresses(self):
        self.assertEqual(len({r.key for r in REGISTER_CATALOG}), len(REGISTER_CATALOG))
        self.assertEqual(
            len({(r.space, r.address) for r in REGISTER_CATALOG}), len(REGISTER_CATALOG)
        )
        for key, spec in NATIVE_SETTINGS.items():
            entry = next(r for r in REGISTER_CATALOG if r.key == key)
            self.assertEqual((entry.space, entry.address, entry.scale), ("holding", spec.address, 0.01))


class NativeSettingTransportTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.connection = MockModbusConnection()
        self.unit = self.connection.for_unit(1)
        self.unit.input.update({1: 4, 8: 2800, 13: 1250})
        self.unit.input.update({20 + i: (2000 - i * 1000) & 0xFFFF for i in range(7)})
        self.unit.holding.update({3: 4500, 4: 2000, 5: 2100, 16: 1800, 302: 1800})
        self.unit.holding.update({6 + i: 2500 + i * 100 for i in range(7)})
        self.writes = []
        self.unit.on_write(self.writes.append)
        self.device = ThermiaCalibra(self.unit)

    async def asyncTearDown(self):
        await self.connection.close()

    async def test_decode_curve_and_limits(self):
        report = await self.device.async_update_readings()
        self.assertIn("heating_settings", report.updated)
        self.assertIn("heating_curve_inputs", report.updated)
        self.assertIn("cooling_settings", report.updated)
        self.assertEqual(self.device.heating_settings.min_supply_temperature, 20)
        self.assertEqual(self.device.heating_settings.max_supply_temperature, 45)
        self.assertEqual(self.device.cooling_settings.passive_cooling_supply_target, 18)
        for i in range(7):
            self.assertEqual(getattr(self.device.heating_settings, f"heat_curve_supply_{i + 1}"), 25 + i)
            self.assertEqual(getattr(self.device.heating_curve_inputs, f"heat_curve_outdoor_{i + 1}"), 20 - i * 10)

    async def test_optional_reads_do_not_expand_existing_ranges(self):
        await self.device.async_update_readings()
        self.assertIn(("holding", 3, 2), [(r.register_type, r.address, r.count) for r in self.unit.read_events])
        self.assertIn(("holding", 6, 7), [(r.register_type, r.address, r.count) for r in self.unit.read_events])
        self.assertIn(("holding", 302, 1), [(r.register_type, r.address, r.count) for r in self.unit.read_events])
        self.assertIn(("input", 20, 7), [(r.register_type, r.address, r.count) for r in self.unit.read_events])

    async def test_every_new_control_uses_the_correct_scaled_register(self):
        values = {"min_supply_temperature": 22, "max_supply_temperature": 48}
        for key, spec in NATIVE_SETTINGS.items():
            value = values.get(key, 20)
            with self.subTest(key=key):
                await self.device.async_write_native_setting(key, value)
                event = self.writes[-1]
                self.assertEqual((event.register_type, event.address, event.values), ("holding", spec.address, [value * 100]))
                self.assertEqual(getattr(getattr(self.device, spec.report_name), key), value)

    async def test_negative_heating_stop_encodes_as_signed_celsius(self):
        await self.device.async_write_native_setting("heating_season_stop_temperature", -5)
        self.assertEqual(self.writes[-1].values, [(-500) & 0xFFFF])
        self.assertEqual(self.device.holding_registers.heating_season_stop_temperature, -5)

    async def test_missing_value_prevents_write(self):
        self.unit.holding[302] = 0x4E20
        await self.device.async_update_readings()
        self.assertIsNone(self.device.cooling_settings.passive_cooling_supply_target)
        with self.assertRaisesRegex(ValueError, "no valid controller readback"):
            await self.device.async_write_native_setting("passive_cooling_supply_target", 18)
        self.assertFalse(self.writes)

    async def test_invalid_requests_never_reach_transport(self):
        for key, value in (("passive_cooling_supply_target", 31), ("min_supply_temperature", 22.5), ("heat_curve_supply_1", float("nan")), ("enable_heat", 20)):
            with self.subTest(key=key), self.assertRaises(ValueError):
                await self.device.async_write_native_setting(key, value)
        self.assertFalse(self.writes)
        self.assertFalse(self.unit.read_events)

    async def test_minimum_and_maximum_are_checked_against_fresh_controller_values(self):
        await self.device.async_update_readings()
        self.unit.holding[3] = 2500
        with self.assertRaisesRegex(ValueError, "minimum must not exceed maximum"):
            await self.device.async_write_native_setting("min_supply_temperature", 30)
        self.unit.holding[4] = 2400
        with self.assertRaises(ValueError):
            await self.device.async_write_native_setting("max_supply_temperature", 23)
        self.assertFalse(self.writes)

    async def test_missing_sibling_limit_prevents_write(self):
        self.unit.holding[3] = 0x4E20
        with self.assertRaises(ValueError):
            await self.device.async_write_native_setting("min_supply_temperature", 20)
        self.assertFalse(self.writes)

    async def test_concurrent_limit_changes_are_serialized(self):
        results = await asyncio.gather(
            self.device.async_write_native_setting("min_supply_temperature", 35),
            self.device.async_write_native_setting("max_supply_temperature", 30),
            return_exceptions=True,
        )
        self.assertIsNone(results[0])
        self.assertIsInstance(results[1], ValueError)
        self.assertEqual(len(self.writes), 1)

    async def test_unconfirmed_write_is_reported(self):
        self.unit.on_write(lambda event: self.unit.holding.update({302: 1800}))
        with self.assertRaisesRegex(ValueError, "not confirmed"):
            await self.device.async_write_native_setting("passive_cooling_supply_target", 20)
        self.assertEqual(self.device.cooling_settings.passive_cooling_supply_target, 18)

    async def test_failed_verification_is_reported(self):
        self.unit.on_write(lambda event: self.unit.fail_read(302, ModbusTimeoutError()))
        with self.assertRaises(ModbusTimeoutError):
            await self.device.async_write_native_setting("passive_cooling_supply_target", 20)

    async def test_failed_initial_read_does_not_write(self):
        self.unit.fail_read(302, IllegalDataAddressError())
        with self.assertRaises(IllegalDataAddressError):
            await self.device.async_write_native_setting("passive_cooling_supply_target", 20)
        self.assertFalse(self.writes)

    async def test_optional_register_failures_preserve_existing_readings(self):
        self.unit.fail_read(3, IllegalDataAddressError())
        self.unit.fail_read(20, IllegalDataAddressError(), register_type="input")
        self.unit.fail_read(302, IllegalDataAddressError())
        report = await self.device.async_update_readings()
        self.assertEqual(set(report.failed), {"heating_settings", "heating_curve_inputs", "cooling_settings"})
        self.assertEqual(set(report.updated), {"input_registers", "holding_registers", "discrete_inputs", "coils", "hot_water_registers"})
        self.assertEqual(self.device.input_registers.outdoor_temperature, 12.5)
        self.assertEqual(self.device.heatpump_status, "Heat")

    async def test_optional_timeout_and_recovery(self):
        self.unit.fail_read(302, ModbusTimeoutError())
        report = await self.device.async_update_readings()
        self.assertIn("cooling_settings", report.failed)
        self.assertIn("input_registers", report.updated)
        self.unit.fail_read(302, None)
        report = await self.device.async_update_readings()
        self.assertIn("cooling_settings", report.updated)
        self.assertNotIn("cooling_settings", report.failed)

    async def test_existing_controls_and_state_remain_usable(self):
        await self.device.async_write_coil("enable_heat", True)
        await self.device.async_write_holding_register("comfort_wheel_setting", 21.5)
        await self.device.async_write_hot_water_register("hot_water_boost", 1)
        self.assertEqual([(w.address, w.values) for w in self.writes], [(9, [True]), (5, [2150]), (6257, [1])])
        await self.device.async_update_readings()
        self.assertTrue(self.device.coils.enable_heat)
        self.assertEqual(self.device.holding_registers.comfort_wheel_setting, 21.5)


if __name__ == "__main__":
    unittest.main()
