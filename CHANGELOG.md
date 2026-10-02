# Changelog

All notable changes to this project are documented here.

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
