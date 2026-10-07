"""Native hot-water requests using the real shared Modbus model library."""

from __future__ import annotations

import asyncio
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "custom_components/thermia_calibra/vendor"))

from modbus_connection import IllegalDataAddressError, ModbusTimeoutError
from modbus_connection.mock import MockModbusConnection

from thermia_calibra_modbus import ThermiaCalibra
from thermia_calibra_modbus.hot_water import validate_hot_water_range


class HotWaterValidationTests(unittest.TestCase):
    def test_boundaries_and_half_degree_steps(self):
        for pair in ((20, 30), (65, 70), (45.5, 58.5)):
            self.assertEqual(validate_hot_water_range(*pair), pair)

    def test_reject_invalid_pairs(self):
        for pair in ((19, 58), (66, 70), (20, 29), (45, 71), (58, 58), (60, 58), (45.1, 58), (45, 58.1)):
            with self.subTest(pair=pair), self.assertRaises(ValueError):
                validate_hot_water_range(*pair)

    def test_reject_invalid_types(self):
        for value in (None, "45", True, False, float("nan"), float("inf")):
            for pair in ((value, 58), (45, value)):
                with self.subTest(pair=pair), self.assertRaises(ValueError):
                    validate_hot_water_range(*pair)

    def test_existing_controller_values_need_not_match_ui_step(self):
        self.assertEqual(validate_hot_water_range(45.25, 58.25, check_step=False), (45.25, 58.25))


class HotWaterTransportTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.connection = MockModbusConnection()
        self.unit = self.connection.for_unit(1)
        self.unit.holding.update({22: 4500, 23: 5800})
        self.unit.input.update({1: 99, 17: 5330})
        self.unit.coils.update({8: True, 9: False, 24: True, 25: False, 33: False})
        self.writes = []
        self.unit.on_write(self.writes.append)
        self.device = ThermiaCalibra(self.unit)

    async def asyncTearDown(self):
        await self.connection.close()

    def temperatures(self):
        return self.unit.holding[22] / 100, self.unit.holding[23] / 100

    async def test_polling_does_not_write(self):
        await self.device.async_update_readings()
        self.assertEqual(self.writes, [])

    async def test_paired_write_scaled_and_confirmed(self):
        await self.device.async_write_hot_water_range(46.5, 59.5)
        self.assertEqual(self.temperatures(), (46.5, 59.5))
        self.assertEqual([(w.address, w.values) for w in self.writes], [(22, [4650]), (23, [5950])])
        self.assertEqual(self.device.holding_registers.stop_temperature_tap_water, 59.5)

    async def test_raise_stop_before_crossing_old_stop(self):
        observed = []
        self.unit.on_write(lambda _: observed.append(self.temperatures()))
        await self.device.async_write_hot_water_range(60, 65)
        self.assertEqual([w.address for w in self.writes], [23, 22])
        self.assertTrue(all(start < stop for start, stop in observed))

    async def test_lower_start_before_crossing_old_start(self):
        observed = []
        self.unit.on_write(lambda _: observed.append(self.temperatures()))
        await self.device.async_write_hot_water_range(25, 35)
        self.assertEqual([w.address for w in self.writes], [22, 23])
        self.assertTrue(all(start < stop for start, stop in observed))

    async def test_unchanged_request_is_read_only(self):
        await self.device.async_write_hot_water_range(45, 58)
        await self.device.async_write_hot_water_enabled(True)
        self.assertEqual(self.writes, [])

    async def test_invalid_request_does_not_write(self):
        with self.assertRaises(ValueError):
            await self.device.async_write_hot_water_range(60, 50)
        self.assertEqual(self.writes, [])

    async def test_invalid_readback_does_not_write(self):
        for pair in ((20000, 5800), (6000, 5800), (4500, 0)):
            self.unit.holding.update({22: pair[0], 23: pair[1]})
            with self.assertRaises(ValueError):
                await self.device.async_write_hot_water_range(45, 60)
        self.assertEqual(self.writes, [])

    async def test_failed_read_does_not_write(self):
        self.unit.fail_read(22, ModbusTimeoutError())
        with self.assertRaises(ModbusTimeoutError):
            await self.device.async_write_hot_water_range(46, 59)
        self.assertEqual(self.writes, [])

    async def test_second_write_failure_leaves_valid_partial_range_and_raises(self):
        self.unit.fail_write(23, IllegalDataAddressError())
        with self.assertRaises(IllegalDataAddressError):
            await self.device.async_write_hot_water_range(46, 59)
        self.assertEqual(self.temperatures(), (46, 58))
        self.assertEqual([w.address for w in self.writes], [22])

    async def test_clamped_write_stops_before_second_write(self):
        self.unit.on_write(lambda event: self.unit.holding.update({22: 4550}) if event.address == 22 else None)
        with self.assertRaisesRegex(ValueError, "not confirmed"):
            await self.device.async_write_hot_water_range(46, 59)
        self.assertEqual([w.address for w in self.writes], [22])

    async def test_external_change_is_not_silently_overwritten(self):
        self.unit.on_write(lambda event: self.unit.holding.update({23: 5700}) if event.address == 22 else None)
        with self.assertRaisesRegex(ValueError, "not confirmed"):
            await self.device.async_write_hot_water_range(46, 59)
        self.assertEqual([w.address for w in self.writes], [22])

    async def test_failed_confirmation_read_raises(self):
        self.unit.on_write(lambda _: self.unit.fail_read(22, ModbusTimeoutError()))
        with self.assertRaises(ModbusTimeoutError):
            await self.device.async_write_hot_water_range(46, 59)
        self.assertEqual([w.address for w in self.writes], [22])

    async def test_concurrent_ranges_are_serialized(self):
        await asyncio.gather(self.device.async_write_hot_water_range(60, 65), self.device.async_write_hot_water_range(25, 35))
        self.assertEqual(self.temperatures(), (25, 35))
        self.assertEqual([w.address for w in self.writes], [23, 22, 22, 23])

    async def test_legacy_control_still_writes_same_register(self):
        await self.device.async_write_holding_register("start_temperature_tap_water", 45.25)
        self.assertEqual([(w.address, w.values) for w in self.writes], [(22, [4525])])

    async def test_mode_only_writes_tap_water_enable(self):
        before = dict(self.unit.coils)
        await self.device.async_write_hot_water_enabled(False)
        self.assertEqual([(w.register_type, w.address, w.values) for w in self.writes], [("coil", 8, [False])])
        self.assertEqual(self.unit.coils, {**before, 8: False})
        self.assertEqual(self.temperatures(), (45, 58))

    async def test_failed_mode_confirmation_raises(self):
        self.unit.on_write(lambda _: self.unit.coils.update({8: True}))
        with self.assertRaisesRegex(ValueError, "not confirmed"):
            await self.device.async_write_hot_water_enabled(False)

    async def test_failed_mode_read_does_not_write(self):
        self.unit.fail_read(8, ModbusTimeoutError(), register_type="coil")
        with self.assertRaises(ModbusTimeoutError):
            await self.device.async_write_hot_water_enabled(False)
        self.assertEqual(self.writes, [])

    async def test_nonboolean_mode_is_rejected(self):
        with self.assertRaises(ValueError):
            await self.device.async_write_hot_water_enabled("off")
        self.assertEqual(self.writes, [])


if __name__ == "__main__":
    unittest.main()
