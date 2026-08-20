"""Tests for the device clock write (Current Time Service 0x2A2B)."""

import asyncio
from datetime import datetime
from unittest.mock import MagicMock, patch
from zoneinfo import ZoneInfo

from bleak.exc import BleakError

from visomat_bt.transport import BleTransport

CTS = "00002a2b-0000-1000-8000-00805f9b34fb"


class _FakeClient:
    def __init__(self):
        self.writes = []

    @property
    def services(self):
        char = MagicMock()
        char.uuid = CTS
        return MagicMock(get_characteristic=lambda uuid: char if uuid == CTS else None)

    async def write_gatt_char(self, uuid, data):
        self.writes.append((uuid, bytes(data)))


def test_set_current_time_writes_cts_payload():
    transport = BleTransport("DD:67:E2:1E:C0:93")
    client = _FakeClient()
    fixed = datetime(2026, 8, 20, 9, 15, 5, tzinfo=ZoneInfo("Europe/Berlin"))
    with patch("visomat_bt.transport.datetime") as mock_dt:
        mock_dt.now.return_value.astimezone.return_value.timetuple.return_value = fixed.timetuple()
        asyncio.run(transport._set_current_time(client))

    assert len(client.writes) == 1
    uuid, payload = client.writes[0]
    assert uuid == CTS
    assert payload[0:2] == bytes([2026 & 0xFF, (2026 >> 8) & 0xFF])
    assert payload[2] == 8  # month
    assert payload[3] == 20  # day
    assert payload[4] == 9  # hour
    assert payload[5] == 15  # minute
    assert payload[6] == 5  # second
    assert payload[7] == 4  # DayOfWeek for Thursday 2026-08-20


def test_set_current_time_skips_without_cts():
    transport = BleTransport("DD:67:E2:1E:C0:93")
    client = MagicMock()
    client.services.get_characteristic.return_value = None
    asyncio.run(transport._set_current_time(client))
    client.write_gatt_char.assert_not_called()


def test_set_current_time_skips_on_unresolved_services():
    transport = BleTransport("DD:67:E2:1E:C0:93")
    client = MagicMock()
    client.services.get_characteristic.side_effect = BleakError("Service Discovery has not been performed yet")
    asyncio.run(transport._set_current_time(client))  # must not raise


def test_set_current_time_failure_is_non_fatal():
    transport = BleTransport("DD:67:E2:1E:C0:93")
    client = MagicMock()
    client.services.get_characteristic.return_value = MagicMock()

    class _FailWriter:
        async def write_gatt_char(self, uuid, data):
            raise BleakError("gatt fail")

    client.write_gatt_char = _FailWriter().write_gatt_char
    asyncio.run(transport._set_current_time(client))  # must not raise
