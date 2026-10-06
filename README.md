# Thermia Calibra Modbus

Unofficial Home Assistant custom integration for Thermia Calibra heat pumps. It uses Home Assistant's native shared Modbus TCP layer, so integrations using the same connection do not open competing Modbus clients.

## Status

This integration is developed and tested on a **Thermia Calibra Cool 7 BW / Genesis**. Other Thermia models may use different registers and are not yet confirmed to work.

The eleven native settings in 0.1.11b1 were read and compared with one physical
Calibra Cool 7 BW controller on 2026-10-06. The heating-season stop was also
written from 17 to 18 C and restored to 17 C on that pump. The other ten writes
and other models have not been physically verified. Register addresses follow
the domestic Genesis 17.1 protocol (ACMBDH01UG0402).

0.1.13b1 is a development candidate focused on direct pump access for
external energy management. It removes the additional automatic thermostats
and presets introduced in 0.1.12b2. Physical controller tests and Home Assistant
validation must pass before a release or installation. The development branch
and draft pull request are for review only; they do not update Home Assistant.

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
- external outdoor-temperature input through Modbus and a selectable source
- optional native heating limits, seven heating-curve points and passive-cooling supply target
- optional hot-water thermostat showing the existing native start/stop range
- 30-second local polling through Home Assistant's shared Modbus connection

Some duplicate or model-specific sensors and the additional-heater-only switch are disabled by default. They can be enabled from the entity settings when needed.

### External outdoor temperature

Thermia calls an externally supplied outdoor temperature a BMS value in its
Modbus documentation. In Home Assistant the integration uses the clearer name
**External outdoor temperature (Modbus)**.

To use it:

1. Write a valid temperature from -50 C up to, but excluding, 200 C to **External Outdoor
   Temperature Input (Modbus)**.
2. Select **External outdoor temperature (Modbus)** as **Outdoor Temperature
   Source**.
3. Keep updating the value at least once every 12 hours. The heat pump falls
   back to its physical PT1000 sensor when the external value is invalid or
   stale.

Select **Physical outdoor sensor (PT1000)** to return to the wired sensor.

### Native heating and cooling settings

The eleven new number entities are disabled by default. Enable individual
entities from the device's entity list after comparing their values with the
controller display. They use the following software limits, which are not
Thermia's documented hardware limits:

| Setting | Holding register | Software range | Step |
| --- | --- | --- | --- |
| Heating season stop temperature | 16 | -10 to 40 C | 1 C |
| Minimum heating supply temperature | 4 | 5 to 65 C | 1 C |
| Maximum heating supply temperature | 3 | 5 to 65 C | 1 C |
| Heating curve supply points 1-7 | 6-12 | 5 to 65 C | 1 C |
| Passive cooling supply target, mixing valve 1 | 302 | 5 to 30 C | 1 C |

Each curve point exposes its corresponding outdoor temperature as an attribute,
read from input registers 20-26. No outdoor-temperature order is assumed.
Unavailable outdoor points do not prevent changing a supported supply point.

Before each native write, the integration reads the setting again. It rejects
invalid values and minimum/maximum combinations, then reads back the controller
value to confirm the write. It does not estimate these values or use optimistic
state updates. Choose heating and cooling temperatures appropriate for your
installation, including any limits configured on the pump itself.

The new heating, curve-input and cooling register groups are polled separately
from the existing groups. An unsupported new group leaves those new entities
unavailable without disabling the established registers. Four additional block
reads are attempted per 30-second poll, even while the new entities are disabled.

### Optional native hot-water control

**Hot water control** is disabled by default. Enable it from the existing
device's entity list to use a thermostat card with the native start and stop
temperatures. The separate number entities, enable switch, device identifiers
and existing automations remain unchanged. This is a view of the pump's native
control, not a second thermostat algorithm or a room-temperature controller.

- **Auto** enables normal tap-water production (coil 8); **Off** disables only
  that production, not the whole pump, heating or anti-legionella protection.
- The lower target is the start temperature (holding register 22); the upper
  target is the stop temperature (23). Both targets must be supplied together.
- Software bounds match the existing controls: start 20..65 C, stop 30..70 C,
  with start strictly below stop. The thermostat uses 0.5 C increments. These
  bounds are not manufacturer limits or a recommendation to change temperatures.
- Current temperature is the weighted tank temperature (input register 17),
  not a room temperature. Activity comes from the pump's current demand.
- No startup, periodic, preset or restoration writes are introduced. No new
  registers or additional periodic reads are needed for this view.

Each requested write is read back. Paired requests are serialized with the
existing tap-water number and switch writes within this integration. Changes
are ordered to keep the intermediate start/stop range valid. Two Modbus writes
are not an atomic transaction: if one fails, the first may already have taken
effect. The request reports an error and refreshes actual state; inspect both
controller temperatures before retrying. There is no automatic rollback that
could overwrite a subsequent controller or external automation change.

Shared transport does not prevent two integrations or automations from changing
the same settings. Avoid conflicting controllers. The separate Genesis
integration's entries and automations are not migrated.

### External energy management

EMHASS or another external planner can schedule heating, hot water and cooling.
Home Assistant automations execute that plan using the direct numbers and
switches. This integration contains no room thermostat algorithm, presets,
charging timers, PV detector or floor-buffer planner. It does not make price,
comfort or appliance-scheduling decisions and performs no periodic, startup or
shutdown policy writes. The native hot-water card's Auto mode means normal
tap-water production is enabled on the pump, not that a second controller runs.

Direct commands read the current control group, write the requested value and
read it back before reporting success. A single boiler start/stop change also
checks the fresh sibling target; it never changes that sibling automatically.
Commands are serialised within this integration, but another integration or
automation can still change the same settings. Verification is not a guarantee
that an external writer will leave the confirmed value unchanged afterwards.

Rejected or unconfirmed requests surface an error and request a state refresh.
There is no policy retry or automatic rollback: after a lost acknowledgement or
failed confirmation, the command may already have been applied. Inspect the
actual pump settings before retrying. Shared Modbus transport may have its own
protocol retry behavior; this integration does not add a second retry loop.
Confirmed enable/Boost registers indicate permission/request, not that the
compressor or the requested cycle has started. Use current operating feedback
separately. Hand-written temperature requests retain 0.01 C register precision;
the existing UI increments remain unchanged. External temperature is still
written when unchanged to renew its pump-side freshness. Exactly 200 C cannot
be written as external temperature: its encoding is the missing-value sentinel.
No external-temperature request automatically selects it as the pump's source.

Safety checks, condensation protection, comfort bounds, minimum operating/rest
times and fallback behavior must remain in the pump and external execution
layer. Removing the beta's optional humidity policy does not remove the need
for physical condensation protection or current humidity measurements.

Operating-state feedback describes the pump's **prioritised demand**, not an
independent measurement of every subsystem. Unknown demand codes remain visible
as `Unknown (code)`; the derived heating, hot-water and anti-legionella states
then become unknown rather than off. A failed register group is unavailable.
Incomplete alarm readings never imply zero alarms. Passive-cooling activity is
an estimate from mixing-valve opening and compressor speed, not a condensation
or flow-safety signal; missing or invalid readings make the estimate unknown.
External execution must require fresh, explicitly recognised states and must
not treat unknown/unavailable values as permission to start the pump.

## Installation

### HACS

Until this integration is included in the default HACS catalogue, add it as a custom repository:

1. Open **HACS** in Home Assistant.
2. Open the menu in the top-right corner and choose **Custom repositories**.
3. Add `https://github.com/renaatdb/thermia-calibra`.
4. Select **Integration** as the type.
5. Find **Thermia Calibra Modbus**, choose **Download**, and restart Home Assistant.

### Manual

Copy `custom_components/thermia_calibra` into `config/custom_components/thermia_calibra`, then restart Home Assistant.

## Configuration

1. Open **Settings -> Devices & services**.
2. Select **Add integration**.
3. Search for **Thermia Calibra Modbus**.
4. Enter the heat pump's host, port and Modbus unit ID.

Defaults are port `502` and unit ID `1`. No separate Modbus YAML hub is required.

## Updating

When installed through HACS, install an offered update and restart Home Assistant. Existing config entries and entity unique IDs are retained.

Before upgrading from 0.1.12b2, safely disable its optional automatic controller
and confirm restoration of temporary pump settings using that version. The new
version reads the old recovery journal without changing or deleting it. If
automatic control is still enabled, settings are still owned, recovery is
pending, or the journal is incomplete, setup stops before opening a connection.
Return to 0.1.12b2 to resolve the issue and inspect the pump; do not delete the
journal to bypass this check. An incomplete journal needs backup-based recovery
and inspection rather than an automatic reset.

Existing numbers, switches, sensors and the native hot-water unique ID are kept.
The beta-only Heating and cooling climate entity is no longer provided. Its
old registry entry may remain unavailable; remove that unused entry only after
checking that no automations depend on it. Other integrations and their
entities are not removed, renamed or migrated by this update.

The display name changed from Thermia Calibra Cool 7 BW to Thermia Calibra Modbus
in 0.1.11. The repository, integration domain `thermia_calibra`, existing entity
keys and device identifiers remain unchanged. Existing device names and entry
titles are retained; new entries use the broader integration name. Do not remove
and recreate your integration to apply this update.

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

Native-setting definitions were adapted from `thermia-genesis-modbus` 0.1.9.
See [third-party notices](THIRD_PARTY_NOTICES.md).
