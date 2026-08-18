"""Configuration loading and validation for the Garmin sync service."""

from __future__ import annotations

from dataclasses import dataclass, field

import yaml


@dataclass
class MqttConfig:
    host: str = "192.168.178.105"
    port: int = 1883
    username: str | None = None
    password: str | None = None
    topic_base: str = "visomat_bt"

    def validate(self) -> None:
        if not self.host:
            raise ValueError("garmin_sync.mqtt.host is required")
        if not self.topic_base:
            raise ValueError("garmin_sync.mqtt.topic_base is required")


@dataclass
class GarminConfig:
    email: str = ""
    password: str = ""
    timezone: str = "Europe/Berlin"
    token_path: str = "~/.garminconnect"

    def validate(self) -> None:
        if not self.email or not self.password:
            raise ValueError("garmin_sync.garmin.email and password are required")


@dataclass
class Config:
    enabled: bool = False
    mqtt: MqttConfig = field(default_factory=MqttConfig)
    garmin: GarminConfig = field(default_factory=GarminConfig)

    def validate(self) -> None:
        if self.enabled:
            self.mqtt.validate()
            self.garmin.validate()


def _section(raw: dict, key: str, default: dataclass):
    data = raw.get(key)
    if data is None:
        return default
    return default.__class__(**{**{f.name: getattr(default, f.name) for f in default.__dataclass_fields__.values()}, **data})


def load_config(path: str = "config.yaml") -> Config:
    with open(path, encoding="utf-8") as handle:
        raw = yaml.safe_load(handle) or {}
    section = raw.get("garmin_sync") or {}
    cfg = Config(
        enabled=bool(section.get("enabled", False)),
        mqtt=_section(section, "mqtt", MqttConfig()),
        garmin=_section(section, "garmin", GarminConfig()),
    )
    cfg.validate()
    return cfg
