"""Configuration loading and validation for the visomat BLE gateway."""

from __future__ import annotations

from dataclasses import dataclass, field

import yaml


@dataclass
class BleConfig:
    # MAC (AA:BB:CC:DD:EE:FF), "auto" or empty to discover by name.
    mac: str = ""
    # Device name substring used when no MAC is configured.
    name: str = "comfort soft"
    adapter: str = "hci0"
    scan_timeout_sec: float = 15.0
    scan_interval_sec: float = 30.0
    reconnect_delay_sec: float = 5.0
    timeout_sec: float = 15.0

    def validate(self) -> None:
        if self.scan_timeout_sec <= 0:
            raise ValueError("ble.scan_timeout_sec must be > 0")
        if self.scan_interval_sec <= 0:
            raise ValueError("ble.scan_interval_sec must be > 0")


@dataclass
class MqttConfig:
    host: str = "core-mosquitto"
    port: int = 1883
    username: str | None = None
    password: str | None = None
    base_topic: str = "visomat_bt"
    discovery_prefix: str = "homeassistant"

    def validate(self) -> None:
        if not self.host:
            raise ValueError("mqtt.host is required")


@dataclass
class Config:
    ble: BleConfig = field(default_factory=BleConfig)
    mqtt: MqttConfig = field(default_factory=MqttConfig)

    def validate(self) -> None:
        self.ble.validate()
        self.mqtt.validate()


def _section(raw: dict, key: str, default: dataclass):
    data = raw.get(key)
    if data is None:
        return default
    return default.__class__(**{**{f.name: getattr(default, f.name) for f in default.__dataclass_fields__.values()}, **data})


def load_config(path: str = "config.yaml") -> Config:
    with open(path, encoding="utf-8") as handle:
        raw = yaml.safe_load(handle) or {}
    visomat = raw.get("visomat") or {}
    cfg = Config(
        ble=_section(visomat, "ble", BleConfig()),
        mqtt=_section(visomat, "mqtt", MqttConfig()),
    )
    cfg.validate()
    return cfg
