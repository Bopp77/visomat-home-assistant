"""MQTT publisher with Home Assistant discovery for the visomat BLE gateway.

Entities are created automatically in Home Assistant via MQTT discovery
(`homeassistant/.../config`). State is published to `visomat_bt/...`. A
measurement publishes systolic/diastolic/MAP/pulse plus optional status flags
as a snapshot; the battery level and the device metadata (0x180A) are
published on every (re)connect.
"""

from __future__ import annotations

import json
import logging
from typing import Any

import paho.mqtt.client as mqtt

from .protocol import BloodPressureMeasurement, feature_labels

LOGGER = logging.getLogger("visomat_bt.publisher")

DEVICE_ID = "visomat_comfort_soft_bt"
DEVICE = {
    "identifiers": [DEVICE_ID],
    "name": "visomat comfort soft BT",
    "manufacturer": "UEBE Medical",
    "model": "comfort soft BT",
    "sw_version": "",
}

STATE_CLASS = "measurement"

SENSORS: dict[str, dict[str, Any]] = {
    "systolic": {"name": "Systole", "unit": "mmHg", "device_class": "pressure", "icon": None},
    "diastolic": {"name": "Diastole", "unit": "mmHg", "device_class": "pressure", "icon": None},
    "map": {"name": "Mittlerer Arterieller Druck", "unit": "mmHg", "device_class": "pressure", "icon": None},
    "pulse": {"name": "Puls", "unit": "bpm", "device_class": "heart_rate", "icon": None},
    "measurement_time": {"name": "Messzeitpunkt", "device_class": "timestamp", "icon": None},
    "user_id": {"name": "Benutzer-ID", "device_class": None, "icon": "mdi:account", "entity_category": "diagnostic"},
    "battery": {"name": "Batterie", "unit": "%", "device_class": "battery", "icon": None},
    "feature": {
        "name": "Unterstützte Funktionen",
        "device_class": None,
        "icon": "mdi:information-outline",
        "entity_category": "diagnostic",
    },
}

STATUS_SENSORS: dict[int, str] = {
    0x0001: "Körperbewegung erkannt",
    0x0002: "Manschette zu locker",
    0x0004: "Unregelmäßiger Puls",
    0x0008: "Puls außerhalb des Bereichs",
    0x0010: "Messposition falsch",
}


class Publisher:
    """Publishes HA discovery configs and state via MQTT."""

    def __init__(self, cfg) -> None:
        self._cfg = cfg
        self._client: mqtt.Client | None = None
        self._connected = False
        self._base = cfg.base_topic
        self._discovery_prefix = cfg.discovery_prefix

    def start(self) -> None:
        client = mqtt.Client(client_id="visomat_bt")
        if self._cfg.username:
            client.username_pw_set(self._cfg.username, self._cfg.password or "")
        client.will_set(self._topic("availability"), "offline", qos=1, retain=True)
        client.on_connect = self._on_connect
        client.connect_async(self._cfg.host, self._cfg.port, keepalive=30)
        client.loop_start()
        self._client = client

    def stop(self) -> None:
        if self._client is not None:
            self._client.loop_stop()
            self._client.disconnect()

    async def publish_measurement(self, measurement: BloodPressureMeasurement) -> None:
        if not self._connected or self._client is None:
            return
        client = self._client
        payloads: list[tuple[str, str]] = []
        if measurement.unit != "mmHg":
            # HA sensors are declared in mmHg; convert kPa measurements.
            factor = 7.50061683
            systolic = measurement.systolic * factor
            diastolic = measurement.diastolic * factor
            map_pressure = measurement.mean_arterial_pressure * factor
        else:
            systolic = measurement.systolic
            diastolic = measurement.diastolic
            map_pressure = measurement.mean_arterial_pressure

        payloads.append((self._topic("sensor/systolic/state"), _format_number(systolic)))
        payloads.append((self._topic("sensor/diastolic/state"), _format_number(diastolic)))
        payloads.append((self._topic("sensor/map/state"), _format_number(map_pressure)))
        if measurement.pulse_rate is not None:
            payloads.append((self._topic("sensor/pulse/state"), _format_number(measurement.pulse_rate)))
        if measurement.timestamp is not None:
            payloads.append((self._topic("sensor/measurement_time/state"), measurement.timestamp.isoformat()))
        if measurement.user_id is not None:
            payloads.append((self._topic("sensor/user_id/state"), str(measurement.user_id)))

        for bit in STATUS_SENSORS:
            payloads.append(
                (self._topic(f"binary_sensor/status_{bit:04x}/state"), "ON" if (measurement.measurement_status or 0) & bit else "OFF")
            )

        for topic, payload in payloads:
            client.publish(topic, payload, qos=0)
        LOGGER.info(
            "published measurement: %s/%s mmHg, pulse %s",
            _format_number(systolic),
            _format_number(diastolic),
            _format_number(measurement.pulse_rate) if measurement.pulse_rate is not None else "?",
        )

    async def publish_battery(self, level: int) -> None:
        if self._connected and self._client is not None:
            self._client.publish(self._topic("sensor/battery/state"), str(level), qos=0)

    async def publish_metadata(self, info) -> None:
        if not self._connected or self._client is None:
            return
        device = dict(DEVICE)
        if info.manufacturer:
            device["manufacturer"] = info.manufacturer
        if info.model:
            device["model"] = info.model
        if info.serial:
            device["serial_number"] = info.serial
        if info.firmware:
            device["sw_version"] = info.firmware
        # Re-publish discovery payloads so HA picks up the enriched device info.
        for payload in self._discovery_payloads(device):
            self._client.publish(payload["topic"], payload["payload"], qos=0, retain=True)
        if info.battery is not None:
            await self.publish_battery(info.battery)
        if info.feature is not None:
            self._client.publish(self._topic("sensor/feature/state"), ", ".join(feature_labels(info.feature)) or str(info.feature), qos=0)

    def _on_connect(self, client, userdata, flags, rc) -> None:
        if rc != 0:
            LOGGER.error("MQTT connect failed with rc=%s", rc)
            self._connected = False
            return
        self._connected = True
        LOGGER.info("MQTT connected")
        for payload in self._discovery_payloads(DEVICE):
            client.publish(payload["topic"], payload["payload"], qos=0, retain=True)
        client.publish(self._topic("availability"), "online", qos=1, retain=True)

    def _topic(self, suffix: str) -> str:
        return f"{self._base}/{suffix}"

    def _discovery_payloads(self, device: dict) -> list[dict]:
        payloads: list[dict] = []
        for key, spec in SENSORS.items():
            config: dict[str, Any] = {
                "name": spec["name"],
                "unique_id": f"{DEVICE_ID}_{key}",
                "state_topic": self._topic(f"sensor/{key}/state"),
                "device": device,
            }
            if spec.get("device_class"):
                config["device_class"] = spec["device_class"]
            if spec.get("unit"):
                config["unit_of_measurement"] = spec["unit"]
            if spec.get("icon"):
                config["icon"] = spec["icon"]
            if spec.get("entity_category"):
                config["entity_category"] = spec["entity_category"]
            if spec.get("device_class") == "timestamp":
                config["state_class"] = "measurement"
            payloads.append(self._discovery("sensor", key, config))

        for bit, label in STATUS_SENSORS.items():
            config = {
                "name": label,
                "unique_id": f"{DEVICE_ID}_status_{bit:04x}",
                "state_topic": self._topic(f"binary_sensor/status_{bit:04x}/state"),
                "device": device,
                "device_class": "problem",
                "entity_category": "diagnostic",
            }
            payloads.append(self._discovery("binary_sensor", f"status_{bit:04x}", config))
        return payloads

    def _discovery(self, component: str, key: str, config: dict) -> dict:
        topic = f"{self._discovery_prefix}/{component}/{DEVICE_ID}/{key}/config"
        return {"topic": topic, "payload": json.dumps(config)}


def _format_number(value: float) -> str:
    if value.is_integer():
        return str(int(value))
    return f"{value:.2f}".rstrip("0").rstrip(".")
