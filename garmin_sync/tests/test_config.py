"""Tests for the Garmin sync configuration loading (incl. HA add-on options)."""

import json

import pytest

from garmin_sync.config import load_ha_options

SAMPLE_OPTIONS = {
    "garmin_sync": {
        "enabled": True,
        "mqtt": {
            "host": "core-mosquitto",
            "port": 1883,
            "username": "bopp",
            "password": "",
            "topic_base": "visomat_bt",
        },
        "garmin": {
            "email": "mein.garmin@example.com",
            "password": "secret",
            "timezone": "Europe/Berlin",
            "token_path": "/data/garminconnect",
        },
    },
}


def test_load_ha_options(tmp_path):
    options = tmp_path / "options.json"
    options.write_text(json.dumps(SAMPLE_OPTIONS), encoding="utf-8")

    cfg = load_ha_options(str(options))

    assert cfg.enabled is True
    assert cfg.mqtt.host == "core-mosquitto"
    assert cfg.mqtt.topic_base == "visomat_bt"
    assert cfg.garmin.email == "mein.garmin@example.com"
    assert cfg.garmin.token_path == "/data/garminconnect"


def test_load_ha_options_defaults_for_missing_sections(tmp_path):
    options = tmp_path / "options.json"
    options.write_text(json.dumps({"garmin_sync": {}}), encoding="utf-8")

    cfg = load_ha_options(str(options))

    assert cfg.enabled is False
    assert cfg.mqtt.host == "192.168.178.105"
    assert cfg.garmin.email == ""


def test_load_ha_options_validates_when_enabled(tmp_path):
    options = tmp_path / "options.json"
    options.write_text(json.dumps({"garmin_sync": {"enabled": True}}), encoding="utf-8")

    with pytest.raises(ValueError):
        load_ha_options(str(options))
