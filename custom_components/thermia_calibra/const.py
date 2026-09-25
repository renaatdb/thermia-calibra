"""Constants for the Thermia Calibra integration."""

from datetime import timedelta

DOMAIN = "thermia_calibra"
MANUFACTURER = "Thermia"
DEVICE_NAME = "Thermia Calibra Cool 7 BW"
DEVICE_MODEL = "Calibra Cool 7 BW / Genesis"
DEFAULT_NAME = DEVICE_NAME
DEFAULT_PORT = 502
DEFAULT_UNIT_ID = 1
CONF_UNIT_ID = "unit_id"
SCAN_INTERVAL = timedelta(seconds=30)

PLATFORMS = ["binary_sensor", "number", "select", "sensor", "switch"]
