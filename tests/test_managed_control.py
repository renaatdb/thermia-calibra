"""Exercise the opt-in bridge with verified reads and refused writes."""

import importlib
import sys
import types
import unittest
from copy import deepcopy
from pathlib import Path

from modbus_connection import IllegalDataAddressError, ModbusTimeoutError

PACKAGE = "calibra_managed_tests"
package = types.ModuleType(PACKAGE)
package.__path__ = [str(Path(__file__).parents[1] / "custom_components/thermia_calibra")]
sys.modules[PACKAGE] = package
bridge = importlib.import_module(f"{PACKAGE}.managed_control")
Control = bridge.ManagedControl


class Unit:
    def __init__(self):
        self.data = {space: {} for space in ("input", "holding", "coil", "discrete")}
        self.reads = []
        self.writes = []
        self.fail_key = None
        self.drop_readback = False

    async def read(self, space, address, count):
        self.reads.append((space, address, count))
        if self.drop_readback:
            raise ModbusTimeoutError()
        if any(key not in self.data[space] for key in range(address, address + count)):
            raise IllegalDataAddressError()
        return [self.data[space][key] for key in range(address, address + count)]

    async def read_input_registers(self, address, count):
        return await self.read("input", address, count)

    async def read_holding_registers(self, address, count):
        return await self.read("holding", address, count)

    async def read_coils(self, address, count):
        return await self.read("coil", address, count)

    async def read_discrete_inputs(self, address, count):
        return await self.read("discrete", address, count)

    async def write_register(self, address, value):
        if self.fail_key == ("holding", address):
            raise ModbusTimeoutError()
        self.data["holding"][address] = value
        self.writes.append(("holding", address, value))

    async def write_coil(self, address, value):
        self.data["coil"][address] = value
        self.writes.append(("coil", address, value))


class ManagedControlTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.unit = Unit()
        self.saved = []
        self.clock = 1000.0
        self.options = {"controller_enabled": True, "confirm_other_controllers_disabled": True}
        self.control = Control(self.unit, self.options, self.persist, now=lambda: self.clock)
        for key, spec in self.control.adapter.specs.items():
            value = {
                "hot_water_enabled": True, "hot_water_start": 45, "hot_water_stop": 58,
                "comfort_wheel": 23, "indoor_temperature": 20, "outdoor_temperature": 10,
                "main_demand": 99, "fixed_supply_target": 30,
                "max_supply_temperature": 37, "min_supply_temperature": 20,
                "heating_season_stop": 17, "passive_cooling_supply_target": 17,
                "hot_water_weighted_temperature": 53, "hot_water_top_temperature": 54,
                "hot_water_lower_temperature": 52,
            }.get(key, 0 if spec.space in ("coil", "discrete") else 27)
            self.unit.data[spec.space][spec.address] = bool(value) if spec.space in ("coil", "discrete") else round(value / spec.scale)
        await self.control.update(20, 10)

    async def persist(self, value):
        self.saved.append(deepcopy(value))

    async def test_disabled_initialization_poll_and_shutdown_do_no_io(self):
        disabled = Control(self.unit, {}, self.persist)
        self.unit.reads.clear()
        await disabled.update(20, 10)
        await disabled.shutdown()
        self.assertEqual(self.unit.reads, [])
        self.assertEqual(self.unit.writes, [])
        with self.assertRaises(ValueError):
            await disabled.command("heating_mode", "heat", 20, 10)

    async def test_requires_explicit_ownership_confirmation(self):
        with self.assertRaises(ValueError):
            Control(self.unit, {"controller_enabled": True}, self.persist)

    async def test_first_enabled_poll_does_not_take_control(self):
        self.assertEqual(self.unit.writes, [])
        self.assertFalse(self.control.engine.state["managed_heating"])
        self.assertFalse(self.control.engine.state["managed_hot_water"])

    async def test_native_catalog_is_restricted_and_boost_requires_confirmation(self):
        self.assertLess(len(self.control.adapter.specs), 30)
        self.assertNotIn("hot_water_boost", self.control.adapter.specs)
        for key in ("anti_legionella_enabled", "immersion_heater", "smart_grid_request"):
            with self.assertRaises(ValueError):
                await self.control._write(key, True)

    async def test_heat_then_cool_never_enables_both_permissions(self):
        await self.control.command("heating_mode", "heat", 20, 10)
        await self.control.command("heating_mode", "cool", 25, 10)
        self.assertFalse(self.unit.data["coil"][9])
        self.assertTrue(self.unit.data["coil"][33])

    async def test_auto_requires_indoor_measurement(self):
        with self.assertRaises(ValueError):
            await self.control.command("heating_mode", "heat_cool", None, 10)
        self.assertEqual(self.unit.writes, [])

    async def test_low_and_vacation_restore_native_dial(self):
        await self.control.command("heating_mode", "heat", 20, 10)
        for preset, expected in (("low", 2100), ("vacation", 1700)):
            await self.control.command("heating_preset", preset, 20, 10)
            self.assertEqual(self.unit.data["holding"][5], expected)
            await self.control.command("heating_preset", "normal", 20, 10)
            self.assertEqual(self.unit.data["holding"][5], 2300)

    async def test_heating_excess_caps_supply_and_restores_originals(self):
        await self.control.command("heating_mode", "heat", 20, 10)
        before = deepcopy(self.unit.data)
        await self.control.command("heating_preset", "pv_charge", 20, 10)
        self.assertTrue(self.unit.data["coil"][41])
        self.assertLessEqual(self.unit.data["holding"][116], self.unit.data["holding"][3])
        self.clock += 13 * 3600
        await self.control.update(20, 10)
        self.assertEqual(self.unit.data["holding"][116], before["holding"][116])
        self.assertEqual(self.unit.data["holding"][16], before["holding"][16])
        self.assertFalse(self.unit.data["coil"][41])

    async def test_water_low_timer_restores_original_pair(self):
        await self.control.command("hot_water_mode", "evening", 20, 10)
        self.assertEqual((self.unit.data["holding"][22], self.unit.data["holding"][23]), (3500, 4000))
        self.clock += 25 * 3600
        await self.control.update(20, 10)
        self.assertEqual((self.unit.data["holding"][22], self.unit.data["holding"][23]), (4500, 5800))

    async def test_water_excess_without_physical_boost_confirmation_writes_nothing(self):
        with self.assertRaises(ValueError):
            await self.control.command("hot_water_mode", "energy_excess", 20, 10)
        self.assertEqual(self.unit.writes, [])

    async def test_confirmed_native_boost_has_fixed_ceiling_and_restores(self):
        self.options["confirm_native_boost"] = True
        self.control = Control(self.unit, self.options, self.persist, now=lambda: self.clock)
        self.unit.data["holding"][6257] = 0
        await self.control.command("hot_water_mode", "energy_excess", 20, 10)
        self.assertEqual(self.unit.data["holding"][6257], 1)
        self.assertEqual(self.unit.data["holding"][23], 6000)
        await self.control.command("hot_water_mode", "auto", 20, 10)
        self.assertEqual(self.unit.data["holding"][6257], 0)
        self.assertEqual(self.unit.data["holding"][23], 5800)

    async def test_external_change_suspends_and_never_overwrites_external_value(self):
        await self.control.command("heating_mode", "heat", 20, 10)
        await self.control.command("heating_preset", "low", 20, 10)
        self.unit.data["holding"][5] = 2400
        before = len(self.unit.writes)
        with self.assertRaisesRegex(ValueError, "outside this thermostat"):
            await self.control.update(20, 10)
        with self.assertRaises(ValueError):
            await self.control.shutdown()
        self.assertEqual(len(self.unit.writes), before)
        self.assertEqual(self.unit.data["holding"][5], 2400)
        self.assertTrue(self.saved[-1]["blocked"])

    async def test_explicit_release_after_inspection_adopts_actual_state_without_writes(self):
        await self.test_external_change_suspends_and_never_overwrites_external_value()
        before = len(self.unit.writes)
        await self.control.release_after_external_change()
        await self.control.update(20, 10)
        self.assertEqual(len(self.unit.writes), before)
        self.assertEqual(self.control.engine.state["heating_target"], 24)
        self.assertFalse(self.control.engine.state["managed_heating"])

    async def test_restart_restores_temporary_profile_with_original_journal(self):
        await self.control.command("heating_mode", "heat", 20, 10)
        await self.control.command("heating_preset", "low", 20, 10)
        saved = deepcopy(self.saved[-1])
        restarted = Control(self.unit, self.options, self.persist, saved, now=lambda: self.clock)
        await restarted.update(20, 10)
        self.assertEqual(self.unit.data["holding"][5], 2300)
        self.assertFalse(restarted.recover_pending)

    async def test_restart_cannot_overwrite_an_external_change(self):
        await self.control.command("heating_mode", "heat", 20, 10)
        saved = deepcopy(self.saved[-1])
        self.unit.data["coil"][9] = False
        restarted = Control(self.unit, self.options, self.persist, saved)
        before = len(self.unit.writes)
        with self.assertRaises(ValueError):
            await restarted.update(20, 10)
        self.assertEqual(len(self.unit.writes), before)

    async def test_store_failure_happens_before_write(self):
        async def fail(value):
            raise OSError("Store unavailable")
        self.control._persist = fail
        with self.assertRaises(OSError):
            await self.control.command("heating_mode", "heat", 20, 10)
        self.assertEqual(self.unit.writes, [])

    async def test_poll_failure_marks_readback_unready(self):
        self.unit.drop_readback = True
        with self.assertRaises(ModbusTimeoutError):
            await self.control.update(20, 10)
        self.assertFalse(self.control.ready)
        self.assertEqual(self.unit.writes, [])

    async def test_measurement_callbacks_resolve_after_current_poll(self):
        await self.control.update(lambda: self.control.value("indoor_temperature"), 10)
        self.assertEqual(self.control.engine._inside, 20)
        self.unit.data["input"][121] = 0x4E20
        await self.control.update(lambda: self.control.value("indoor_temperature"), 10)
        self.assertIsNone(self.control.engine._inside)

    async def test_unsupported_actions_cannot_reach_unrelated_engine_commands(self):
        with self.assertRaises(ValueError):
            await self.control.command("anti_legionella", False, 20, 10)
        self.assertEqual(self.unit.writes, [])

    async def test_invalid_options_cannot_enable_a_controller(self):
        for options in ({"controller_enabled": "yes"}, {"sensor_timeout": float("nan")},
                        {"hot_water_evening_start": True}, {"hysteresis": float("inf")},
                        {"hot_water_evening_start": 45, "hot_water_evening_stop": 40}):
            with self.subTest(options=options), self.assertRaises(ValueError):
                Control(self.unit, self.options | options, self.persist)

    async def test_failed_write_preserves_unconfirmed_intent_before_io(self):
        self.unit.fail_key = ("holding", 5)
        with self.assertRaises(ModbusTimeoutError):
            await self.control._write("comfort_wheel", 21)
        self.assertEqual(self.saved[-1]["ownership"]["comfort_wheel"],
            {"before": 23, "after": 21, "confirmed": False})
        self.assertEqual(self.unit.data["holding"][5], 2300)
        self.unit.fail_key = None
        restarted = Control(self.unit, self.options, self.persist, self.saved[-1])
        await restarted.update(20, 10)
        self.assertIsNone(restarted.blocked)

    async def test_lost_write_reply_can_be_verified_after_restart(self):
        original = self.unit.write_register
        async def lost_reply(address, value):
            await original(address, value)
            raise ModbusTimeoutError()
        self.unit.write_register = lost_reply
        with self.assertRaises(ModbusTimeoutError):
            await self.control._write("comfort_wheel", 21)
        saved = deepcopy(self.saved[-1])
        self.assertFalse(saved["ownership"]["comfort_wheel"]["confirmed"])
        self.unit.write_register = original
        restarted = Control(self.unit, self.options, self.persist, saved)
        await restarted.update(20, 10)
        self.assertTrue(restarted.ownership["comfort_wheel"]["confirmed"])
        self.assertIsNone(restarted.blocked)

    async def test_external_change_between_poll_and_write_is_never_overwritten(self):
        self.unit.data["holding"][5] = 2400
        with self.assertRaisesRegex(ValueError, "changed during this request"):
            await self.control._write("comfort_wheel", 21)
        self.assertEqual(self.unit.writes, [])
        self.assertEqual(self.unit.data["holding"][5], 2400)

    async def test_partial_water_profile_failure_restores_only_owned_values(self):
        self.unit.fail_key = ("holding", 23)
        with self.assertRaises(ModbusTimeoutError):
            await self.control.command("hot_water_mode", "evening", 20, 10)
        self.unit.fail_key = None
        restarted = Control(self.unit, self.options, self.persist, self.saved[-1])
        await restarted.update(20, 10)
        self.assertEqual((self.unit.data["holding"][22], self.unit.data["holding"][23]), (4500, 5800))


if __name__ == "__main__":
    unittest.main()
