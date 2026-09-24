# Thermia Calibra

Home Assistant custom integration for Thermia Calibra heat pumps using the native shared Modbus layer.

## Status

Tested on:

- Thermia Calibra Cool 7 BW

## Architecture

This integration uses Home Assistant's shared Modbus connection through `async_get_unit`.

That means Modbus communication is handled by Home Assistant's native Modbus layer instead of opening a separate Modbus TCP client.

## Features

Current support includes:

- temperature sensors
- compressor and circulation pump data
- enable heat
- enable passive cooling
- enable tap water
- hot water temperature settings
- hot water and anti-legionella operational status
- selected operational status entities

## Installation

Copy:

`custom_components/thermia_calibra`

to:

`config/custom_components/thermia_calibra`

Restart Home Assistant and add the integration via:

**Settings -> Devices & services -> Add integration -> Thermia Calibra**

## Disclaimer

This integration is currently developed and tested specifically with a Thermia Calibra Cool 7 BW. Other Thermia models may require different Modbus registers.
