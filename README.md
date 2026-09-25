# Thermia Calibra

Unofficial Home Assistant custom integration for Thermia Calibra heat pumps. It uses Home Assistant's native shared Modbus TCP layer, so integrations using the same connection do not open competing Modbus clients.

## Status

This integration is developed and tested on a **Thermia Calibra Cool 7 BW / Genesis**. Other Thermia models may use different registers and are not yet confirmed to work.

Requirements:

- Home Assistant 2026.9.0 or newer
- Modbus TCP enabled on the heat pump
- network access from Home Assistant to the heat pump
- the heat pump's IP address, Modbus TCP port and unit ID

## Features

- temperature, compressor, circulation pump and operating-hour sensors
- active alarm count and anti-legionella warning
- heating, hot-water, anti-legionella and passive-cooling operating status
- controls for heating, passive cooling, tap water and anti-legionella
- hot-water boost
- comfort-wheel and hot-water temperature settings
- BMS outdoor temperature and selected outdoor-temperature source
- 30-second local polling through Home Assistant's shared Modbus connection

Some duplicate or model-specific sensors and the additional-heater-only switch are disabled by default. They can be enabled from the entity settings when needed.

## Installation

### HACS

Until this integration is included in the default HACS catalogue, add it as a custom repository:

1. Open **HACS** in Home Assistant.
2. Open the menu in the top-right corner and choose **Custom repositories**.
3. Add `https://github.com/renaatdb/thermia-calibra`.
4. Select **Integration** as the type.
5. Find **Thermia Calibra**, choose **Download**, and restart Home Assistant.

### Manual

Copy `custom_components/thermia_calibra` into `config/custom_components/thermia_calibra`, then restart Home Assistant.

## Configuration

1. Open **Settings -> Devices & services**.
2. Select **Add integration**.
3. Search for **Thermia Calibra Cool 7 BW**.
4. Enter the heat pump's host, port and Modbus unit ID.

Defaults are port `502` and unit ID `1`. No separate Modbus YAML hub is required.

## Updating

When installed through HACS, install an offered update and restart Home Assistant. Existing config entries and entity unique IDs are retained.

## Safety

This integration contains writable controls. Changing heating, cooling, tap-water or anti-legionella settings can affect comfort, energy use and hot-water hygiene.

- Confirm register compatibility before using it with another Thermia model.
- Test automations with conservative limits and verify the reported state after each write.
- Keep the heat pump's own safety controls enabled.
- Do not expose Modbus TCP directly to the internet.

## Troubleshooting

- **Cannot connect:** verify the IP address, port, unit ID and that Modbus TCP is enabled and reachable from Home Assistant.
- **Entities are unavailable:** inspect the Home Assistant log and confirm that no other application is competing for the Modbus connection.
- **Some values are unknown:** the tested model does not return every optional register in every installation.
- **HACS shows no icon:** Home Assistant uses the bundled icon, but current HACS versions may still show a placeholder for locally bundled custom-integration branding.

Please report problems through [GitHub Issues](https://github.com/renaatdb/thermia-calibra/issues). Include the Home Assistant version, heat-pump model, integration version and relevant log lines. Do not include passwords, tokens or other secrets.

## Architecture

The integration obtains its unit through Home Assistant's `async_get_unit` API and uses `modbus-connection` for device-specific register access. Equal connection details are pooled by Home Assistant, which serializes requests over one shared connection.

## Disclaimer

This is an independent community project and is not affiliated with or endorsed by Thermia. Use it at your own risk. Thermia names and marks belong to their respective owner.

## License

Released under the [MIT License](LICENSE).
