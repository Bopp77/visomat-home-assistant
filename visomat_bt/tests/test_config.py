"""Tests for configuration loading (config.yaml and HA add-on options.json)."""

import json

import pytest

from visomat_bt.config import load_config, load_ha_options

SAMPLE_OPTIONS = {
    "log_level": "info",
    "visomat": {
        "ble": {
            "mac": "DD:67:E2:1E:C0:93",
            "name": "comfort soft",
            "adapter": "hci0",
            "scan_timeout_sec": 5,
            "scan_interval_sec": 2,
            "reconnect_delay_sec": 1,
            "timeout_sec": 15,
        },
        "mqtt": {
            "host": "core-mosquitto",
            "port": 1883,
            "username": "visomat",
            "password": "",
            "base_topic": "visomat_bt",
            "discovery_prefix": "homeassistant",
        },
    },
}


def test_load_ha_options(tmp_path):
    options = tmp_path / "options.json"
    options.write_text(json.dumps(SAMPLE_OPTIONS), encoding="utf-8")

    cfg = load_ha_options(str(options))

    assert cfg.ble.mac == "DD:67:E2:1E:C0:93"
    assert cfg.ble.scan_timeout_sec == 5
    assert cfg.ble.scan_interval_sec == 2
    assert cfg.mqtt.host == "core-mosquitto"
    assert cfg.mqtt.username == "visomat"
    assert cfg.mqtt.base_topic == "visomat_bt"


def test_load_ha_options_defaults_for_missing_sections(tmp_path):
    options = tmp_path / "options.json"
    options.write_text(json.dumps({"visomat": {}}), encoding="utf-8")

    cfg = load_ha_options(str(options))

    assert cfg.ble.mac == ""
    assert cfg.ble.name == "comfort soft"
    assert cfg.mqtt.host == "core-mosquitto"
    assert cfg.mqtt.discovery_prefix == "homeassistant"


def test_load_ha_options_validates(tmp_path):
    options = tmp_path / "options.json"
    options.write_text(json.dumps({"visomat": {"ble": {"scan_timeout_sec": 0}}}), encoding="utf-8")

    with pytest.raises(ValueError):
        load_ha_options(str(options))


def test_load_config_falls_back_to_ha_options(monkeypatch, tmp_path):
    options = tmp_path / "options.json"
    options.write_text(json.dumps(SAMPLE_OPTIONS), encoding="utf-8")
    monkeypatch.setattr("visomat_bt.config.HA_OPTIONS_PATH", str(options))

    cfg = load_config(str(tmp_path / "missing.yaml"))

    assert cfg.ble.mac == "DD:67:E2:1E:C0:93"
