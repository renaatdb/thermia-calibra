"""Read-only state interpretation must not turn missing data into permission."""

from itertools import product
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "custom_components/thermia_calibra/vendor"))

from thermia_calibra_modbus import ThermiaCalibra
from modbus_connection.mock import MockModbusConnection
from thermia_calibra_modbus.readings import THERMIA_MISSING_VALUE


class OperatingStatusTests(unittest.TestCase):
    def setUp(self):
        # Interpret decoded values without a transport or any possible pump write.
        self.device = ThermiaCalibra.__new__(ThermiaCalibra)
        self.device.input_registers = SimpleNamespace(
            first_prioritised_demand=None,
            mix_valve_cooling_opening_degree=None,
            compressor_speed_rpm=None,
        )
        self.device.discrete_inputs = SimpleNamespace(
            alarm_active_class_a=None,
            alarm_active_class_b=None,
            alarm_active_class_c=None,
        )

    def states(self):
        return (
            self.device.hot_water_operational,
            self.device.heat_operational,
            self.device.anti_legionella_operational,
        )

    def test_all_known_demand_codes_keep_existing_meaning(self):
        for code, label in self.device.HEATPUMP_STATUS_BY_CODE.items():
            with self.subTest(code=code):
                self.device.input_registers.first_prioritised_demand = code
                self.assertEqual(self.device.heatpump_status, label)
                self.assertEqual(self.states(), (code == 3, code == 4, code == 7))

    def test_unknown_codes_remain_visible_without_false_inactive_states(self):
        for code in (0, 9, 42, -1, 32767):
            with self.subTest(code=code):
                self.device.input_registers.first_prioritised_demand = code
                self.assertEqual(self.device.heatpump_status, f"Unknown ({code})")
                self.assertEqual(self.states(), (None, None, None))

    def test_invalid_demand_values_are_not_coerced_to_known_codes(self):
        for value in (None, True, False, "4", 4.0, 4.5, float("nan"), float("inf")):
            with self.subTest(value=value):
                self.device.input_registers.first_prioritised_demand = value
                self.assertIsNone(self.device.heatpump_status)
                self.assertEqual(self.states(), (None, None, None))

    def test_complete_alarm_count(self):
        for values in product((False, True), repeat=3):
            with self.subTest(values=values):
                self.set_alarms(values)
                self.assertEqual(self.device.active_alarms, sum(values))

    def test_missing_alarm_classes_never_report_a_complete_count(self):
        for values in product((None, False, True), repeat=3):
            if None in values:
                with self.subTest(values=values):
                    self.set_alarms(values)
                    self.assertIsNone(self.device.active_alarms)

    def set_alarms(self, values):
        for field, value in zip(("a", "b", "c"), values):
            setattr(self.device.discrete_inputs, f"alarm_active_class_{field}", value)

    def test_passive_cooling_estimate_keeps_existing_valid_meaning(self):
        for valve, rpm, expected in ((0, 0, False), (1, 0, True), (100, 0, True), (50, 1200, False), (0, 1200, False)):
            with self.subTest(valve=valve, rpm=rpm):
                self.set_cooling(valve, rpm)
                self.assertIs(self.device.passive_cooling_active, expected)

    def test_invalid_cooling_readings_never_report_inactive(self):
        invalid = (None, True, "0", float("nan"), float("inf"), -1)
        for value in invalid:
            for valve, rpm in ((value, 0), (0, value)):
                with self.subTest(valve=valve, rpm=rpm):
                    self.set_cooling(valve, rpm)
                    self.assertIsNone(self.device.passive_cooling_active)
        self.set_cooling(101, 0)
        self.assertIsNone(self.device.passive_cooling_active)

    def set_cooling(self, valve, rpm):
        self.device.input_registers.mix_valve_cooling_opening_degree = valve
        self.device.input_registers.compressor_speed_rpm = rpm


class OperatingStatusTransportTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.connection = MockModbusConnection()
        self.unit = self.connection.for_unit(1)
        self.device = ThermiaCalibra(self.unit)
        self.writes = []
        self.unit.on_write(self.writes.append)

    async def asyncTearDown(self):
        await self.connection.close()

    async def test_decoded_demand_and_missing_sentinel_are_read_only(self):
        for raw, expected in (
            (3, (True, False, False)),
            (4, (False, True, False)),
            (7, (False, False, True)),
            (99, (False, False, False)),
            (42, (None, None, None)),
            (THERMIA_MISSING_VALUE, (None, None, None)),
        ):
            with self.subTest(raw=raw):
                self.unit.input[1] = raw
                await self.device.input_registers.async_update(notify=False)
                self.assertEqual((
                    self.device.hot_water_operational,
                    self.device.heat_operational,
                    self.device.anti_legionella_operational,
                ), expected)
        self.assertEqual(self.writes, [])

    async def test_decoded_cooling_values_and_sentinels_are_read_only(self):
        for valve, rpm, expected in (
            (25, 0, True), (0, 0, False), (25, 1500, False),
            (THERMIA_MISSING_VALUE, 0, None),
            (25, THERMIA_MISSING_VALUE, None), (101, 0, None),
        ):
            with self.subTest(valve=valve, rpm=rpm):
                self.unit.input.update({137: valve, 5: rpm})
                await self.device.input_registers.async_update(notify=False)
                self.assertIs(self.device.passive_cooling_active, expected)
        self.assertEqual(self.writes, [])


if __name__ == "__main__":
    unittest.main()
