"""Blood Pressure Service (0x1810) parsing for the visomat comfort soft BT.

The device follows the Bluetooth SIG Blood Pressure Service 1.x layout.
Measurements arrive as notifications/indications on characteristic 0x2A35:

    Flags(1) Systolic(2) Diastolic(2) MAP(2)
    [Timestamp(7)] [PulseRate(2)] [UserID(1)] [MeasurementStatus(2)]

Presence of the optional fields is signalled by flag bits 1..4. All pressure
and pulse values are IEEE-11073 16-bit SFLOAT (little-endian): 12-bit two's
complement mantissa + 4-bit two's complement exponent, value = mantissa * 10^exp.
The device sends mmHg values, which decode as plain integers (exponent 0).

Also parsed: Blood Pressure Feature (0x2A49, uint16) which advertises which
measurement-status bits the device actually reports.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

BLOOD_PRESSURE_SERVICE_UUID = "00001810-0000-1000-8000-00805f9b34fb"
BLOOD_PRESSURE_MEASUREMENT_UUID = "00002a35-0000-1000-8000-00805f9b34fb"
BLOOD_PRESSURE_FEATURE_UUID = "00002a49-0000-1000-8000-00805f9b34fb"
BATTERY_SERVICE_UUID = "0000180f-0000-1000-8000-00805f9b34fb"
BATTERY_LEVEL_UUID = "00002a19-0000-1000-8000-00805f9b34fb"

UNIT_MMHG = "mmHg"
UNIT_KPA = "kPa"

# Flag bits of the Blood Pressure Measurement characteristic.
FLAG_UNITS_KPA = 0x01
FLAG_TIMESTAMP = 0x02
FLAG_PULSE_RATE = 0x04
FLAG_USER_ID = 0x08
FLAG_MEASUREMENT_STATUS = 0x10

# Measurement Status bit labels (bit 0 = LSB).
MEASUREMENT_STATUS_LABELS: dict[int, str] = {
    0x0001: "Körperbewegung erkannt",
    0x0002: "Manschette zu locker",
    0x0004: "Unregelmäßiger Puls",
    0x0008: "Puls außerhalb des Bereichs",
    0x0010: "Messposition falsch",
}

# Blood Pressure Feature (0x2A49) bit labels.
FEATURE_LABELS: dict[int, str] = {
    0x0001: "Erkennung Körperbewegung",
    0x0002: "Erkennung Manschetten-Sitz",
    0x0004: "Erkennung unregelmäßiger Puls",
    0x0008: "Erkennung Puls außerhalb Bereich",
    0x0010: "Erkennung Messposition",
    0x0020: "Multiple Bonds",
}


class ProtocolError(ValueError):
    """Raised when a BLS payload is malformed or shorter than required."""


@dataclass(frozen=True)
class BloodPressureMeasurement:
    """A decoded Blood Pressure Measurement (0x2A35) value."""

    systolic: float
    diastolic: float
    mean_arterial_pressure: float
    unit: str
    timestamp: datetime | None = None
    pulse_rate: float | None = None
    user_id: int | None = None
    measurement_status: int | None = None

    @property
    def status_labels(self) -> list[str]:
        """Human-readable labels for the reported measurement-status bits."""
        if self.measurement_status is None:
            return []
        return [label for bit, label in MEASUREMENT_STATUS_LABELS.items() if self.measurement_status & bit]


def parse_sfloat(data: bytes) -> float:
    """Decode a 16-bit IEEE-11073 SFLOAT (little-endian)."""
    if len(data) < 2:
        raise ProtocolError("SFLOAT requires 2 bytes")
    raw = int.from_bytes(data[:2], "little")
    mantissa = raw & 0x0FFF
    exponent = (raw >> 12) & 0x0F
    if mantissa >= 0x0800:
        mantissa -= 0x1000
    if exponent >= 0x08:
        exponent -= 0x10
    if mantissa == 0x07FF or exponent == 0x08:
        raise ProtocolError("SFLOAT NaN")
    return mantissa * (10.0**exponent)


def parse_measurement(data: bytes) -> BloodPressureMeasurement:
    """Parse a Blood Pressure Measurement (0x2A35) notification payload."""
    if len(data) < 7:
        raise ProtocolError(f"measurement too short: {len(data)} bytes")
    flags = data[0]
    unit = UNIT_KPA if flags & FLAG_UNITS_KPA else UNIT_MMHG
    systolic = parse_sfloat(data[1:3])
    diastolic = parse_sfloat(data[3:5])
    map_pressure = parse_sfloat(data[5:7])

    offset = 7
    timestamp = None
    pulse_rate = None
    user_id = None
    measurement_status = None

    if flags & FLAG_TIMESTAMP:
        if len(data) < offset + 7:
            raise ProtocolError("missing timestamp field")
        year = int.from_bytes(data[offset : offset + 2], "little")
        month, day, hour, minute, second = data[offset + 2 : offset + 7]
        try:
            timestamp = datetime(year, month, day, hour, minute, second)
        except ValueError as exc:
            raise ProtocolError(f"invalid timestamp: {exc}") from exc
        offset += 7

    if flags & FLAG_PULSE_RATE:
        if len(data) < offset + 2:
            raise ProtocolError("missing pulse rate field")
        pulse_rate = parse_sfloat(data[offset : offset + 2])
        offset += 2

    if flags & FLAG_USER_ID:
        if len(data) < offset + 1:
            raise ProtocolError("missing user id field")
        user_id = data[offset]
        offset += 1

    if flags & FLAG_MEASUREMENT_STATUS:
        if len(data) < offset + 2:
            raise ProtocolError("missing measurement status field")
        measurement_status = int.from_bytes(data[offset : offset + 2], "little")
        offset += 2

    return BloodPressureMeasurement(
        systolic=systolic,
        diastolic=diastolic,
        mean_arterial_pressure=map_pressure,
        unit=unit,
        timestamp=timestamp,
        pulse_rate=pulse_rate,
        user_id=user_id,
        measurement_status=measurement_status,
    )


def parse_feature(data: bytes) -> int:
    """Parse the Blood Pressure Feature (0x2A49) uint16 value."""
    if len(data) < 2:
        raise ProtocolError("feature requires 2 bytes")
    return int.from_bytes(data[:2], "little")


def feature_labels(feature: int) -> list[str]:
    """Human-readable labels for supported Blood Pressure Feature bits."""
    return [label for bit, label in FEATURE_LABELS.items() if feature & bit]
