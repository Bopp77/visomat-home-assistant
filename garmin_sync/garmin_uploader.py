"""Garmin Connect uploader with deduplication.

Wraps the `garminconnect` library. Authentication is done once (interactively
via the `--login` CLI flag when MFA is enabled), afterwards the cached tokens
in `~/.garminconnect/` are reused. Measurements are deduplicated against
Garmin's stored values via `get_blood_pressure()` to avoid duplicates when the
visomat re-delivers stored measurements on connect.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from garminconnect import Garmin, GarminConnectAuthenticationError, GarminConnectConnectionError

from .mqtt_listener import Measurement

LOGGER = logging.getLogger("garmin_sync.garmin_uploader")


class GarminUploader:
    """Handles Garmin authentication and blood pressure uploads."""

    def __init__(self, cfg) -> None:
        self._cfg = cfg
        self._client: Garmin | None = None

    def login(self, prompt_mfa=None) -> None:
        """Log in, using cached tokens or (optionally) a MFA prompt callback.

        For interactive/initial login pass a `prompt_mfa` callable (see
        ``main.py --login``). In normal operation the cached tokens from
        ``~/.garminconnect/`` are reused, so no MFA is triggered.
        """
        tokenstore = str(Path(self._cfg.token_path).expanduser())
        client = Garmin(self._cfg.email, self._cfg.password, prompt_mfa=prompt_mfa)
        client.login(tokenstore=tokenstore)
        self._client = client
        LOGGER.info("Garmin login successful (display: %s)", client.display_name)

    def is_authenticated(self) -> bool:
        return self._client is not None

    def sync_measurement(self, measurement: Measurement) -> bool:
        """Upload a measurement if it is not already present in Garmin."""
        if self._client is None:
            raise RuntimeError("not authenticated")
        date_str = measurement.measurement_time.astimezone(UTC).date().isoformat()
        existing = self._get_blood_pressure(date_str)
        if self._already_present(existing, measurement):
            LOGGER.info(
                "measurement %s already in Garmin, skipping",
                measurement.measurement_time.isoformat(),
            )
            return False

        local_ts = self._to_local_iso(measurement.measurement_time)
        LOGGER.info(
            "uploading %s: %s/%s mmHg, pulse %s",
            local_ts,
            measurement.systolic,
            measurement.diastolic,
            measurement.pulse,
        )
        self._client.set_blood_pressure(
            systolic=measurement.systolic,
            diastolic=measurement.diastolic,
            pulse=measurement.pulse,
            timestamp=local_ts,
        )
        return True

    def _get_blood_pressure(self, date_str: str) -> list[dict]:
        if self._client is None:
            return []
        try:
            data = self._client.get_blood_pressure(date_str)
        except (GarminConnectConnectionError, GarminConnectAuthenticationError) as exc:
            LOGGER.warning("get_blood_pressure failed, skipping dedupe: %s", exc)
            return []
        if not isinstance(data, dict):
            return []
        for section in ("bloodPressureList", "bpmList", "data"):
            values = data.get(section)
            if isinstance(values, list):
                return values
        return []

    def _already_present(self, existing: list[dict], measurement: Measurement) -> bool:
        target = _fmt_gmt(measurement.measurement_time)
        for entry in existing:
            stamp = (
                entry.get("measurementTimestampGMT")
                or entry.get("measurementTimestamp")
                or ""
            )
            if stamp and stamp.startswith(target[:19]):
                return True
        return False

    def _to_local_iso(self, measurement_time: datetime) -> str:
        local = measurement_time.astimezone(ZoneInfo(self._cfg.timezone))
        return local.isoformat(timespec="milliseconds")


def _fmt_gmt(dt: datetime) -> str:
    return dt.astimezone(UTC).isoformat(timespec="milliseconds")
