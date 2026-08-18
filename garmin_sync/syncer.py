"""Coordinates MQTT listener and Garmin uploader."""

from __future__ import annotations

import logging

from .garmin_uploader import GarminUploader
from .mqtt_listener import MqttListener

LOGGER = logging.getLogger("garmin_sync.syncer")


class Syncer:
    """Wires MQTT measurements into Garmin uploads."""

    def __init__(self, cfg) -> None:
        self._cfg = cfg
        self._uploader = GarminUploader(cfg.garmin)
        self._listener: MqttListener | None = None

    def login(self) -> None:
        self._uploader.login(prompt_mfa=None)

    def login_interactive(self) -> None:
        def prompt_mfa() -> str:
            return input("MFA-Code: ").strip()

        self._uploader.login(prompt_mfa=prompt_mfa)

    def start(self) -> None:
        self._listener = MqttListener(self._cfg.mqtt, self._on_measurement)
        self._listener.start()

    def stop(self) -> None:
        if self._listener is not None:
            self._listener.stop()

    def _on_measurement(self, measurement) -> None:
        try:
            self._uploader.sync_measurement(measurement)
        except Exception as exc:  # noqa: BLE001 - keep the listener alive on any Garmin error
            LOGGER.error("garmin sync failed: %s", exc)
