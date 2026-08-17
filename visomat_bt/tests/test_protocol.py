"""Protocol tests for the visomat BLS (Blood Pressure Service) parser.

Hex vectors derived from the Bluetooth SIG BLS 1.1.1 layout and the
device's GATT dump (Blood Pressure Service 0x1810, characteristic 0x2A35).
"""

from datetime import datetime

import pytest

from visomat_bt.protocol import (
    MEASUREMENT_STATUS_LABELS,
    ProtocolError,
    parse_feature,
    parse_measurement,
    parse_sfloat,
)

# 120/80 mmHg, MAP 93, Puls 72, Timestamp 2024-12-24 14:30:05.
# Flags 0x06: mmHg, Timestamp + Pulse Rate present.
VECTOR = bytes.fromhex("06 78 00 50 00 5D 00 E8 07 0C 18 0E 1E 05 48 00")


def test_parse_sfloat_plain_integer():
    assert parse_sfloat(bytes.fromhex("78 00")) == 120.0
    assert parse_sfloat(bytes.fromhex("50 00")) == 80.0
    assert parse_sfloat(bytes.fromhex("5D 00")) == 93.0


def test_parse_sfloat_negative_mantissa():
    # -1 with exponent 0 -> mantissa 0xFFF, exponent 0.
    assert parse_sfloat(bytes.fromhex("FF 0F")) == -1.0


def test_parse_sfloat_exponent():
    # 12.5 -> mantissa 125, exponent -1 (0xF) => bytes 7D F0.
    assert parse_sfloat(bytes.fromhex("7D F0")) == 12.5


def test_parse_sfloat_requires_two_bytes():
    with pytest.raises(ProtocolError):
        parse_sfloat(b"\x00")


def test_parse_measurement_full_vector():
    m = parse_measurement(VECTOR)
    assert m.systolic == 120.0
    assert m.diastolic == 80.0
    assert m.mean_arterial_pressure == 93.0
    assert m.unit == "mmHg"
    assert m.timestamp == datetime(2024, 12, 24, 14, 30, 5)
    assert m.pulse_rate == 72.0
    assert m.user_id is None
    assert m.measurement_status is None
    assert m.status_labels == []


def test_parse_measurement_minimal():
    # Only the mandatory fields: flags=0x00, 120/80, MAP 93.
    m = parse_measurement(bytes.fromhex("00 78 00 50 00 5D 00"))
    assert m.systolic == 120.0
    assert m.timestamp is None
    assert m.pulse_rate is None


def test_parse_measurement_kpa_unit():
    # flags=0x01 (kPa), values 16.0 / 10.7 / 12.4 mmHg-equivalents irrelevant.
    m = parse_measurement(bytes.fromhex("01 00 01 00 00 00 00"))
    assert m.unit == "kPa"


def test_parse_measurement_user_and_status():
    # flags=0x18 (User ID + Measurement Status), 120/80, MAP 93,
    # user id 2, status 0x0004 (irregular pulse).
    m = parse_measurement(bytes.fromhex("18 78 00 50 00 5D 00 02 04 00"))
    assert m.user_id == 2
    assert m.measurement_status == 0x0004
    assert m.status_labels == [MEASUREMENT_STATUS_LABELS[0x0004]]


def test_parse_measurement_too_short():
    with pytest.raises(ProtocolError):
        parse_measurement(b"\x00\x01\x02")


def test_parse_measurement_missing_optional_field():
    # Flag claims a timestamp but payload ends early.
    with pytest.raises(ProtocolError):
        parse_measurement(bytes.fromhex("02 78 00 50 00 5D 00 E8 07"))


def test_parse_feature():
    assert parse_feature(bytes.fromhex("07 00")) == 0x0007
    with pytest.raises(ProtocolError):
        parse_feature(b"\x01")
