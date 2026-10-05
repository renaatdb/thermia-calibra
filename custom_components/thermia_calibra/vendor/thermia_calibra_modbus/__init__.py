"""Thermia Calibra / Genesis Modbus device library."""

from .device import ThermiaCalibra, UpdateReport
from .register_catalog import REGISTER_CATALOG, RegisterDefinition
from .readings import (
    GenesisCoils,
    GenesisCoolingSettings,
    GenesisDiscreteInputs,
    GenesisHeatingCurveInputs,
    GenesisHeatingSettings,
    GenesisHoldingRegisters,
    GenesisHotWaterRegisters,
    GenesisInputRegisters,
)

__all__ = [
    "GenesisCoils",
    "GenesisCoolingSettings",
    "GenesisDiscreteInputs",
    "GenesisHeatingCurveInputs",
    "GenesisHeatingSettings",
    "GenesisHoldingRegisters",
    "GenesisHotWaterRegisters",
    "GenesisInputRegisters",
    "REGISTER_CATALOG",
    "RegisterDefinition",
    "ThermiaCalibra",
    "UpdateReport",
]
