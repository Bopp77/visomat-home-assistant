"""Tests for the Garmin uploader (dedupe and payload handling)."""

from datetime import UTC, datetime

from garmin_sync.garmin_uploader import GarminUploader, _fmt_gmt
from garmin_sync.mqtt_listener import Measurement


class _FakeGarmin:
    def __init__(self):
        self.uploaded = []
        self.stored = {}

    def get_blood_pressure(self, date_str):
        return {"bloodPressureList": self.stored.get(date_str, [])}

    def set_blood_pressure(self, **kwargs):
        self.uploaded.append(kwargs)


class _FakeConfig:
    def __init__(self):
        self.email = "a@b.de"
        self.password = "secret"
        self.timezone = "Europe/Berlin"
        self.token_path = "~/.garminconnect"


def _measurement(hour=20, minute=0, systolic=120, diastolic=80, pulse=60):
    return Measurement(
        measurement_time=datetime(2026, 8, 18, hour, minute, tzinfo=UTC),
        systolic=systolic,
        diastolic=diastolic,
        pulse=pulse,
    )


def test_upload_when_not_present():
    uploader = GarminUploader(_FakeConfig())
    fake = _FakeGarmin()
    uploader._client = fake
    result = uploader.sync_measurement(_measurement())
    assert result is True
    assert len(fake.uploaded) == 1
    payload = fake.uploaded[0]
    assert payload["systolic"] == 120
    assert payload["diastolic"] == 80
    assert payload["pulse"] == 60
    assert payload["timestamp"].startswith("2026-08-18T22:00")  # UTC+2 Europe/Berlin


def test_upload_skipped_when_already_present():
    uploader = GarminUploader(_FakeConfig())
    fake = _FakeGarmin()
    existing_gmt = _fmt_gmt(_measurement().measurement_time)
    fake.stored["2026-08-18"] = [{"measurementTimestampGMT": existing_gmt}]
    uploader._client = fake
    result = uploader.sync_measurement(_measurement())
    assert result is False
    assert fake.uploaded == []


def test_upload_requires_auth():
    uploader = GarminUploader(_FakeConfig())
    try:
        uploader.sync_measurement(_measurement())
    except RuntimeError as exc:
        assert "not authenticated" in str(exc)
    else:
        raise AssertionError("expected RuntimeError")
