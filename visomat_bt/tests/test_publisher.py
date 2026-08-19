"""Publisher tests with a mock MQTT client."""

import asyncio
from datetime import datetime
from unittest.mock import MagicMock

from visomat_bt.config import MqttConfig
from visomat_bt.protocol import parse_measurement
from visomat_bt.publisher import DEVICE, Publisher

VECTOR = bytes.fromhex("06 78 00 50 00 5D 00 E8 07 0C 18 0E 1E 05 48 00")


def _publisher() -> tuple[Publisher, MagicMock]:
    publisher = Publisher(MqttConfig(host="localhost", base_topic="visomat_bt"))
    publisher._client = MagicMock()
    publisher._connected = True
    return publisher, publisher._client


def test_discovery_payloads_cover_all_sensors():
    publisher, _ = _publisher()
    topics = [payload["topic"] for payload in publisher._discovery_payloads(dict(DEVICE))]
    assert any(topic.endswith("/systolic/config") for topic in topics)
    assert any(topic.endswith("/diastolic/config") for topic in topics)
    assert any(topic.endswith("/map/config") for topic in topics)
    assert any(topic.endswith("/pulse/config") for topic in topics)
    assert any(topic.endswith("/measurement_time/config") for topic in topics)
    assert any(topic.endswith("/battery/config") for topic in topics)
    assert any(topic.endswith("/feature/config") for topic in topics)
    assert any(topic.endswith("/status_0004/config") for topic in topics)


def test_publish_measurement_full_vector():
    publisher, client = _publisher()
    measurement = parse_measurement(VECTOR)
    asyncio.run(publisher.publish_measurement(measurement))

    topics = [call[0][0] for call in client.publish.call_args_list]
    published = {topic: payload for topic, payload, *_ in [call[0] for call in client.publish.call_args_list]}

    assert topics.count("visomat_bt/sensor/systolic/state") == 1
    assert published["visomat_bt/sensor/systolic/state"] == "120"
    assert published["visomat_bt/sensor/diastolic/state"] == "80"
    assert published["visomat_bt/sensor/map/state"] == "93"
    assert published["visomat_bt/sensor/pulse/state"] == "72"
    expected_time = datetime(2024, 12, 24, 14, 30, 5).astimezone().isoformat()
    assert published["visomat_bt/sensor/measurement_time/state"] == expected_time


def test_publish_measurement_kpa_conversion():
    publisher, client = _publisher()
    measurement = parse_measurement(bytes.fromhex("01 00 01 00 00 00 00"))
    measurement = measurement.__class__(
        systolic=16.0,
        diastolic=10.7,
        mean_arterial_pressure=12.4,
        unit="kPa",
    )
    asyncio.run(publisher.publish_measurement(measurement))

    published = {topic: payload for topic, payload, *_ in [call[0] for call in client.publish.call_args_list]}
    assert published["visomat_bt/sensor/systolic/state"] == "120.01"
    assert published["visomat_bt/sensor/diastolic/state"] == "80.26"


def test_publish_battery():
    publisher, client = _publisher()
    asyncio.run(publisher.publish_battery(87))
    assert client.publish.call_args_list[0][0][0] == "visomat_bt/sensor/battery/state"
    assert client.publish.call_args_list[0][0][1] == "87"


def test_publish_measurement_status_bits():
    publisher, client = _publisher()
    measurement = parse_measurement(bytes.fromhex("18 78 00 50 00 5D 00 02 04 00"))
    asyncio.run(publisher.publish_measurement(measurement))

    published = {topic: payload for topic, payload, *_ in [call[0] for call in client.publish.call_args_list]}
    assert published["visomat_bt/binary_sensor/status_0004/state"] == "ON"
    assert published["visomat_bt/binary_sensor/status_0001/state"] == "OFF"
    assert published["visomat_bt/sensor/user_id/state"] == "2"
