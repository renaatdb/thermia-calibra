"""Direct pump commands require readback, without retries or implicit policy."""

import asyncio
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "custom_components/thermia_calibra/vendor"))

from modbus_connection import IllegalDataAddressError, ModbusTimeoutError
from modbus_connection.mock import MockModbusConnection
from thermia_calibra_modbus import ThermiaCalibra


COILS = {
    "enable_tap_water": 8, "enable_heat": 9, "enable_anti_legionella": 24,
    "enable_additional_heater_only": 25, "enable_passive_cooling": 33,
}
NUMBERS = {
    "comfort_wheel_setting": (5, 21.5, 2150),
    "start_temperature_tap_water": (22, 46.25, 4625),
    "stop_temperature_tap_water": (23, 59.5, 5950),
    "outdoor_temperature_source": (117, 1, 1),
    "bms_outdoor_temperature": (118, -12.3, (-1230) & 0xFFFF),
}


class DirectCommandTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.connection = MockModbusConnection()
        self.unit = self.connection.for_unit(1)
        self.unit.holding.update({5: 2300, 22: 4500, 23: 5800, 117: 0, 118: 1230, 6257: 0})
        self.device = ThermiaCalibra(self.unit)
        self.writes = []
        self.unit.on_write(self.writes.append)

    async def asyncTearDown(self):
        await self.connection.close()

    async def test_every_coil_is_read_written_and_read_back(self):
        for field, address in COILS.items():
            for enabled in (True, False):
                with self.subTest(field=field, enabled=enabled):
                    self.unit.read_events.clear()
                    await self.device.async_write_coil(field, enabled)
                    self.assertEqual((self.writes[-1].register_type, self.writes[-1].address, self.writes[-1].values), ("coil", address, [enabled]))
                    self.assertIs(getattr(self.device.coils, field), enabled)
                    self.assertGreaterEqual(sum(event.register_type == "coil" and event.address == address for event in self.unit.read_events), 2)

    async def test_every_direct_number_is_scaled_and_confirmed(self):
        for field, (address, value, raw) in NUMBERS.items():
            with self.subTest(field=field):
                self.unit.read_events.clear()
                await self.device.async_write_holding_register(field, value)
                self.assertEqual((self.writes[-1].address, self.writes[-1].values), (address, [raw]))
                self.assertAlmostEqual(getattr(self.device.holding_registers, field), value)
                self.assertGreaterEqual(sum(event.register_type == "holding" and event.address == address for event in self.unit.read_events), 2)

    async def test_explicit_boost_request_is_binary_and_confirmed(self):
        for value in (1, 0):
            await self.device.async_write_hot_water_register("hot_water_boost", value)
            self.assertEqual((self.writes[-1].address, self.writes[-1].values), (6257, [value]))
            self.assertEqual(self.device.hot_water_registers.hot_water_boost, value)

    async def test_nonboolean_coil_requests_never_reach_transport(self):
        for value in ("off", "false", 0, 1, None, float("nan")):
            with self.subTest(value=value), self.assertRaises(ValueError):
                await self.device.async_write_coil("enable_heat", value)
        self.assertEqual(self.writes, [])
        self.assertEqual(self.unit.read_events, [])

    async def test_invalid_numeric_requests_never_reach_transport(self):
        requests = (
            ("comfort_wheel_setting", True), ("comfort_wheel_setting", "21"),
            ("comfort_wheel_setting", None), ("comfort_wheel_setting", float("inf")),
            ("comfort_wheel_setting", float("nan")), ("comfort_wheel_setting", 21.001),
            ("comfort_wheel_setting", 9), ("comfort_wheel_setting", 41),
            ("start_temperature_tap_water", 19), ("stop_temperature_tap_water", 71),
            ("outdoor_temperature_source", 0.5), ("outdoor_temperature_source", 2),
            ("bms_outdoor_temperature", -51), ("bms_outdoor_temperature", 201),
            ("bms_outdoor_temperature", 200),
        )
        for field, value in requests:
            with self.subTest(field=field, value=value), self.assertRaises(ValueError):
                await self.device.async_write_holding_register(field, value)
        for value in (True, "1", None, 0.5, -1, 2):
            with self.subTest(boost=value), self.assertRaises(ValueError):
                await self.device.async_write_hot_water_register("hot_water_boost", value)
        self.assertEqual(self.writes, [])
        self.assertEqual(self.unit.read_events, [])

    async def test_unknown_or_readonly_fields_do_not_reach_transport(self):
        for method, field, value in (
            (self.device.async_write_coil, "enable_something", True),
            (self.device.async_write_holding_register, "missing", 20),
            (self.device.async_write_holding_register, "cooling_start_temperature", 20),
            (self.device.async_write_hot_water_register, "missing", 1),
        ):
            with self.subTest(field=field), self.assertRaises(AttributeError):
                await method(field, value)
        self.assertEqual(self.writes, [])
        self.assertEqual(self.unit.read_events, [])

    async def test_single_boiler_targets_use_fresh_sibling_and_do_not_adjust_it(self):
        await self.device.async_update_readings()
        self.unit.holding[23] = 4800
        with self.assertRaisesRegex(ValueError, "start temperature must be below stop"):
            await self.device.async_write_holding_register("start_temperature_tap_water", 50)
        self.unit.holding.update({22: 5500, 23: 5800})
        with self.assertRaises(ValueError):
            await self.device.async_write_holding_register("stop_temperature_tap_water", 54)
        self.assertEqual(self.writes, [])

    async def test_valid_single_target_can_repair_an_invalid_existing_pair(self):
        self.unit.holding[22] = 6000
        await self.device.async_write_holding_register("start_temperature_tap_water", 45)
        self.assertEqual([(event.address, event.values) for event in self.writes], [(22, [4500])])
        self.assertEqual(self.unit.holding[23], 5800)

    async def test_missing_target_or_sibling_prevents_boiler_write(self):
        for address in (22, 23):
            with self.subTest(address=address):
                self.unit.holding.update({22: 4500, 23: 5800, address: 0x4E20})
                with self.assertRaises(ValueError):
                    await self.device.async_write_holding_register("start_temperature_tap_water", 46)
        self.assertEqual(self.writes, [])

    async def test_boiler_sibling_change_is_reported_without_restoration(self):
        self.unit.on_write(lambda _: self.unit.holding.update({23: 5700}))
        with self.assertRaisesRegex(ValueError, "not confirmed"):
            await self.device.async_write_holding_register("start_temperature_tap_water", 46)
        self.assertEqual([(event.address, event.values) for event in self.writes], [(22, [4600])])
        self.assertEqual(self.unit.holding[23], 5700)

    async def test_first_external_temperature_can_initialize_a_missing_value(self):
        self.unit.holding[118] = 0x4E20
        await self.device.async_write_holding_register("bms_outdoor_temperature", 15)
        self.assertEqual(self.device.holding_registers.bms_outdoor_temperature, 15)
        self.assertEqual(self.unit.holding[117], 0)

    async def test_unchanged_external_temperature_is_still_written_for_freshness(self):
        for _ in range(2):
            await self.device.async_write_holding_register("bms_outdoor_temperature", 12.3)
        self.assertEqual([(event.address, event.values) for event in self.writes], [(118, [1230]), (118, [1230])])

    async def test_missing_comfort_or_boost_prevents_write(self):
        self.unit.holding.update({5: 0x4E20, 6257: 0x4E20})
        for method, field, value in (
            (self.device.async_write_holding_register, "comfort_wheel_setting", 22),
            (self.device.async_write_hot_water_register, "hot_water_boost", 1),
        ):
            with self.subTest(field=field), self.assertRaisesRegex(ValueError, "no valid controller readback"):
                await method(field, value)
        self.assertEqual(self.writes, [])

    async def test_failed_initial_read_does_not_write(self):
        for method, field, value, address, space in (
            (self.device.async_write_coil, "enable_heat", True, 9, "coil"),
            (self.device.async_write_holding_register, "comfort_wheel_setting", 22, 5, "holding"),
            (self.device.async_write_hot_water_register, "hot_water_boost", 1, 6257, "holding"),
        ):
            with self.subTest(field=field):
                self.unit.fail_read(address, ModbusTimeoutError(), register_type=space)
                with self.assertRaises(ModbusTimeoutError):
                    await method(field, value)
                self.unit.fail_read(address, None, register_type=space)
        self.assertEqual(self.writes, [])

    async def test_rejected_writes_are_not_retried(self):
        for method, field, value, address, space in (
            (self.device.async_write_coil, "enable_heat", True, 9, "coil"),
            (self.device.async_write_holding_register, "comfort_wheel_setting", 22, 5, "holding"),
            (self.device.async_write_hot_water_register, "hot_water_boost", 1, 6257, "holding"),
        ):
            with self.subTest(field=field):
                self.unit.fail_write(address, IllegalDataAddressError(), register_type=space)
                with self.assertRaises(IllegalDataAddressError):
                    await method(field, value)
                self.unit.fail_write(address, None, register_type=space)
        self.assertEqual(self.writes, [])

    async def test_unconfirmed_values_are_reported_without_retry_or_undo(self):
        for method, field, value, address, store, original in (
            (self.device.async_write_coil, "enable_heat", True, 9, self.unit.coils, False),
            (self.device.async_write_holding_register, "comfort_wheel_setting", 22, 5, self.unit.holding, 2300),
            (self.device.async_write_hot_water_register, "hot_water_boost", 1, 6257, self.unit.holding, 0),
        ):
            with self.subTest(field=field):
                unsubscribe = self.unit.on_write(lambda _, s=store, a=address, v=original: s.update({a: v}))
                before = len(self.writes)
                with self.assertRaisesRegex(ValueError, "not confirmed"):
                    await method(field, value)
                self.assertEqual(len(self.writes), before + 1)
                self.assertEqual(store[address], original)
                unsubscribe()

    async def test_failed_confirmation_may_leave_applied_value_and_never_undoes(self):
        for method, field, value, address, space, store, raw in (
            (self.device.async_write_coil, "enable_heat", True, 9, "coil", self.unit.coils, True),
            (self.device.async_write_holding_register, "comfort_wheel_setting", 22, 5, "holding", self.unit.holding, 2200),
            (self.device.async_write_hot_water_register, "hot_water_boost", 1, 6257, "holding", self.unit.holding, 1),
        ):
            with self.subTest(field=field):
                unsubscribe = self.unit.on_write(lambda _, a=address, s=space: self.unit.fail_read(a, ModbusTimeoutError(), register_type=s))
                before = len(self.writes)
                with self.assertRaises(ModbusTimeoutError):
                    await method(field, value)
                self.assertEqual(len(self.writes), before + 1)
                self.assertEqual(store[address], raw)
                unsubscribe()
                self.unit.fail_read(address, None, register_type=space)

    async def test_concurrent_single_boiler_changes_cannot_cross_targets(self):
        result = await asyncio.gather(
            self.device.async_write_holding_register("start_temperature_tap_water", 55),
            self.device.async_write_holding_register("stop_temperature_tap_water", 54),
            return_exceptions=True,
        )
        self.assertIsNone(result[0])
        self.assertIsInstance(result[1], ValueError)
        self.assertEqual([(event.address, event.values) for event in self.writes], [(22, [5500])])

    async def test_lost_write_acknowledgement_never_retries_an_applied_command(self):
        for method, field, value, writer_name, address, store, raw in (
            (self.device.async_write_coil, "enable_heat", True, "write_coil", 9, self.unit.coils, True),
            (self.device.async_write_holding_register, "comfort_wheel_setting", 22, "write_register", 5, self.unit.holding, 2200),
            (self.device.async_write_hot_water_register, "hot_water_boost", 1, "write_register", 6257, self.unit.holding, 1),
        ):
            with self.subTest(field=field):
                original_write = getattr(self.unit, writer_name)

                async def apply_then_timeout(address, value):
                    await original_write(address, value)
                    raise ModbusTimeoutError()

                before = len(self.writes)
                with patch.object(self.unit, writer_name, side_effect=apply_then_timeout):
                    with self.assertRaises(ModbusTimeoutError):
                        await method(field, value)
                self.assertEqual(len(self.writes), before + 1)
                self.assertEqual(store[address], raw)

    async def test_generic_entrypoint_cannot_bypass_native_limit_validation(self):
        self.unit.holding.update({3: 2500, 4: 2000})
        with self.assertRaisesRegex(ValueError, "minimum must not exceed maximum"):
            await self.device.async_write_holding_register("min_supply_temperature", 30)
        self.assertEqual(self.writes, [])


if __name__ == "__main__":
    unittest.main()
