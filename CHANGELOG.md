# Changelog

All notable changes to this project are documented here.

## 0.1.12b2 - Unreleased development candidate

- Add a disabled-by-default heating/cooling thermostat and an explicit opt-in
  automatic controller for both thermostat entities.
- Heating supports Normal, Excess Energy, Low Mode and Vacation. Cooling
  supports Normal and Vacation; combined mode restricts energy/low profiles
  to heating. Hot water supports Normal, Excess Energy and timed Low Mode.
- Reuse the MIT-licensed Genesis 0.1.12 control policy with a restricted
  register/command adapter and the existing Home Assistant shared transport.
- Persist temporary settings and write intentions, verify readback, recover
  after restart and pause persistently on externally changed owned values.
- Require explicit confirmation that competing controllers are disabled.
  Leave all existing Genesis/EMHASS entities and automations untouched.
- Native hot-water Boost at register 6257 requires separate physical
  verification and confirmation; its source-policy ceiling remains 60 C.
- Add temperature/humidity freshness checks, optional cooling humidity guard,
  English/Dutch options and real Home Assistant/pure-policy regression tests.
- Physical tests of the new controller remain outstanding. No installation,
  stable release or changes to the already published b1 tag are implied.

## 0.1.12b1 - 2026-10-06 (Pre-release)

- Add an optional, disabled-by-default native hot-water climate entity with
  auto/off modes, paired start/stop targets and weighted tank temperature.
- Preserve all existing numbers, switches, entry and device identifiers.
- Validate paired writes, serialize with legacy tap-water controls, order
  changes to maintain a valid intermediate range and verify controller readback.
- Refresh actual state on errors, including partially applied changes; do not
  automatically roll back or run a second control algorithm.
- Add English/Dutch labels and transport/real Home Assistant regression tests.
- No PV, vacation, low-mode policy engine or automatic migration is included.
- Physical validation of this thermostat is still required. No stable release
  has been published from this candidate.

### Physical validation of 0.1.11b1 on 2026-10-06

- User confirmed all eleven native read values on a Calibra Cool 7 BW.
- Heating-season stop was tested at 17 -> 18 -> 17 C, including pump readback.
- User reported no Modbus problems in filtered Home Assistant logs. The other
  ten writes and other models remain unverified.

## 0.1.11b1 - 2026-10-05 (Pre-release)

- Rename the visible integration and HACS entry to Thermia Calibra Modbus.
- Retain the repository, domain, existing entity keys and device identifiers.
- Add eleven disabled-by-default native temperature controls: heating season
  stop, minimum/maximum heating supply, seven heating-curve points, and the
  passive-cooling supply target for mixing valve 1.
- Expose the matching outdoor temperature on each heating-curve control.
- Isolate optional register groups, validate writes and confirm controller
  readback; prevent minimum supply from exceeding maximum supply.
- Add English/Dutch labels and simulated Modbus regression tests.
- These new controls require validation on a physical Calibra Cool 7 BW before
  publishing a stable release. Other Calibra models are not yet verified.

## 0.1.10 - 2026-10-02

- Add a control for the externally supplied outdoor temperature on Modbus
  register 118.
- Add a selector for the physical PT1000 or external Modbus outdoor-temperature
  source on register 117.
- Replace the ambiguous user-facing term BMS with External outdoor temperature
  (Modbus), while retaining the official Thermia register terminology internally.
- Keep the former read-only source sensor disabled by default for compatibility.

## 0.1.9 - 2026-09-25

- Use the tested model name, Thermia Calibra Cool 7 BW, consistently in HACS and the public documentation.
- Replace the low-resolution artwork with the sharp 256x256 Thermia icon from Home Assistant Brands.

## 0.1.8 - 2026-09-25

- Prepare the integration for public HACS installation.
- Document requirements, configuration, safety and troubleshooting.
- Add English and Dutch custom-integration translations.
- Add repository validation workflows, issue metadata and an MIT license.

## 0.1.7 - 2026-09-24

- Add heating operational status derived from the Thermia demand state.

## 0.1.6 - 2026-09-24

- Add hot-water and anti-legionella operational status.

## 0.1.5 - 2026-09-24

- Add BMS / Zehnder outdoor-temperature support.

## 0.1.0 - 2026-09-19

- Initial Thermia Calibra Cool 7 BW integration.
