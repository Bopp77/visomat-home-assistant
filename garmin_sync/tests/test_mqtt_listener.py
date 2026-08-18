"""Tests for MQTT measurement assembly and topic parsing."""

from datetime import UTC, datetime

from garmin_sync.config import MqttConfig
from garmin_sync.mqtt_listener import MqttListener, _topic_key


class _FakeConfig:
    def __init__(self):
        self.host = "localhost"
        self.port = 1883
        self.username = None
        self.password = None
        self.topic_base = "visomat_bt"


def test_topic_key_parses_valid_topic():
    assert _topic_key("visomat_bt/sensor/systolic/state", "visomat_bt") == "systolic"
    assert _topic_key("visomat_bt/sensor/measurement_time/state", "visomat_bt") == "measurement_time"


def test_topic_key_rejects_unrelated_topic():
    assert _topic_key("other/sensor/systolic/state", "visomat_bt") == ""
    assert _topic_key("visomat_bt/availability", "visomat_bt") == ""
    assert _topic_key("visomat_bt/sensor/x/config", "visomat_bt") == ""


def test_measurement_assembled_when_complete():
    received = []
    listener = MqttListener(MqttConfig(topic_base="visomat_bt"), received.append)
    listener._latest = {}

    listener._on_message(None, None, _msg("systolic", "120"))
    listener._on_message(None, None, _msg("diastolic", "80"))
    assert received == []

    listener._on_message(None, None, _msg("pulse", "60"))
    listener._on_message(None, None, _msg("measurement_time", "2026-08-18T20:00:00+00:00"))
    assert len(received) == 1
    m = received[0]
    assert m.systolic == 120
    assert m.diastolic == 80
    assert m.pulse == 60
    assert m.measurement_time == datetime(2026, 8, 18, 20, 0, tzinfo=UTC)


def test_measurement_deduped_when_redelivered_after_reconnect():
    received = []
    listener = MqttListener(MqttConfig(topic_base="visomat_bt"), received.append)
    for _ in range(2):  # simulate the visomat re-delivering on reconnect
        listener._on_message(None, None, _msg("systolic", "130"))
        listener._on_message(None, None, _msg("diastolic", "85"))
        listener._on_message(None, None, _msg("pulse", "58"))
        listener._on_message(None, None, _msg("measurement_time", "2026-08-18T20:05:00+00:00"))
    assert len(received) == 1  # same measurement_time only emitted once


def test_distinct_measurements_both_emitted():
    received = []
    listener = MqttListener(MqttConfig(topic_base="visomat_bt"), received.append)
    listener._on_message(None, None, _msg("systolic", "130"))
    listener._on_message(None, None, _msg("diastolic", "85"))
    listener._on_message(None, None, _msg("pulse", "58"))
    listener._on_message(None, None, _msg("measurement_time", "2026-08-18T20:05:00+00:00"))
    listener._on_message(None, None, _msg("systolic", "135"))
    listener._on_message(None, None, _msg("diastolic", "87"))
    listener._on_message(None, None, _msg("pulse", "61"))
    listener._on_message(None, None, _msg("measurement_time", "2026-08-18T20:10:00+00:00"))
    assert len(received) == 2


def test_unparsable_measurement_is_skipped():
    received = []
    listener = MqttListener(MqttConfig(topic_base="visomat_bt"), received.append)
    listener._on_message(None, None, _msg("systolic", "abc"))
    listener._on_message(None, None, _msg("diastolic", "80"))
    listener._on_message(None, None, _msg("pulse", "60"))
    listener._on_message(None, None, _msg("measurement_time", "2026-08-18T20:00:00+00:00"))
    assert received == []


def _msg(key: str, value: str):
    class _Msg:
        topic = f"visomat_bt/sensor/{key}/state"
        payload = value.encode()

    return _Msg()
