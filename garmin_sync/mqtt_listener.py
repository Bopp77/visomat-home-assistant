"""MQTT listener that assembles complete visomat measurements.

The visomat gateway publishes each sensor value on its own topic
(`<base>/sensor/systolic/state`, `<base>/sensor/diastolic/state`,
`<base>/sensor/pulse/state`, `<base>/sensor/measurement_time/state`).
This listener remembers the latest value per topic and emits a complete
measurement once all four fields are available. The measurement_time (UTC
ISO from the device) is used as the identity/deduplication key.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime

import paho.mqtt.client as mqtt

LOGGER = logging.getLogger("garmin_sync.mqtt_listener")

TOPICS = ("systolic", "diastolic", "pulse", "measurement_time")


@dataclass(frozen=True)
class Measurement:
    """A complete blood pressure measurement."""

    measurement_time: datetime
    systolic: int
    diastolic: int
    pulse: int


MeasurementHandler = Callable[[Measurement], None]


class MqttListener:
    """Subscribes to visomat MQTT topics and assembles measurements."""

    def __init__(self, cfg, on_measurement: MeasurementHandler) -> None:
        self._cfg = cfg
        self._on_measurement = on_measurement
        self._latest: dict[str, str] = {}
        self._last_emitted: datetime | None = None
        self._client: mqtt.Client | None = None

    def start(self) -> None:
        client = mqtt.Client(client_id="garmin_sync")
        if self._cfg.username:
            client.username_pw_set(self._cfg.username, self._cfg.password or "")
        client.on_connect = self._on_connect
        client.on_message = self._on_message
        client.connect_async(self._cfg.host, self._cfg.port, keepalive=30)
        client.loop_start()
        self._client = client

    def stop(self) -> None:
        if self._client is not None:
            self._client.loop_stop()
            self._client.disconnect()

    def _on_connect(self, client, userdata, flags, rc) -> None:
        if rc != 0:
            LOGGER.error("MQTT connect failed with rc=%s", rc)
            return
        LOGGER.info("MQTT connected to %s:%s", self._cfg.host, self._cfg.port)
        for key in TOPICS:
            client.subscribe(f"{self._cfg.topic_base}/sensor/{key}/state", qos=0)

    def _on_message(self, client, userdata, msg) -> None:
        key = _topic_key(msg.topic, self._cfg.topic_base)
        if key not in TOPICS:
            return
        payload = msg.payload.decode("utf-8", errors="replace").strip()
        self._latest[key] = payload
        if all(k in self._latest for k in TOPICS):
            measurement = self._build()
            if measurement is not None and measurement.measurement_time != self._last_emitted:
                self._last_emitted = measurement.measurement_time
                self._on_measurement(measurement)

    def _build(self) -> Measurement | None:
        try:
            systolic = int(self._latest["systolic"])
            diastolic = int(self._latest["diastolic"])
            pulse = int(self._latest["pulse"])
            measurement_time = datetime.fromisoformat(self._latest["measurement_time"])
        except (ValueError, TypeError) as exc:
            LOGGER.warning("unparsable measurement, skipping: %s", exc)
            return None
        return Measurement(
            measurement_time=measurement_time,
            systolic=systolic,
            diastolic=diastolic,
            pulse=pulse,
        )


def _topic_key(topic: str, topic_base: str) -> str:
    prefix = f"{topic_base}/sensor/"
    if not topic.startswith(prefix):
        return ""
    rest = topic[len(prefix) :]
    if not rest.endswith("/state"):
        return ""
    return rest[: -len("/state")]
