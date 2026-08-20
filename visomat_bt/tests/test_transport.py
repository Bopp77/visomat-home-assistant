"""Tests for the device clock write (Current Time Service 0x2A2B)."""

import asyncio
from datetime import datetime
from unittest.mock import MagicMock, patch
from zoneinfo import ZoneInfo

from bleak.exc import BleakError

from visomat_bt.transport import BleTransport


class _FakeClient:
    def __init__(self):
        self.writes = []

    async def write_gatt_char(self, uuid, data):
        self.writes.append((uuid, bytes(data)))


def test_set_current_time_writes_cts_payload():
    transport = BleTransport("DD:67:E2:1E:C0:93")
    transport._client = MagicMock()
    transport._has_uuid = MagicMock(return_value=True)
    client = _FakeClient()
    fixed = datetime(2026, 8, 20, 9, 15, 5, tzinfo=ZoneInfo("Europe/Berlin"))
    with patch("visomat_bt.transport.datetime") as mock_dt:
        mock_dt.now.return_value.astimezone.return_value.timetuple.return_value = fixed.timetuple()
        asyncio.run(transport._set_current_time(client))

    assert len(client.writes) == 1
    uuid, payload = client.writes[0]
    assert uuid == "00002a2b-0000-1000-8000-00805f9b34fb"
    assert payload[0:2] == bytes([2026 & 0xFF, (2026 >> 8) & 0xFF])
    assert payload[2] == 8  # month
    assert payload[3] == 20  # day
    assert payload[4] == 9  # hour
    assert payload[5] == 15  # minute
    assert payload[6] == 5  # second
    assert payload[7] == 4  # DayOfWeek for Thursday 2026-08-20


def test_set_current_time_skips_without_cts():
    transport = BleTransport("DD:67:E2:1E:C0:93")
    transport._client = MagicMock()
    transport._has_uuid = MagicMock(return_value=False)
    client = _FakeClient()
    asyncio.run(transport._set_current_time(client))
    assert client.writes == []


def test_set_current_time_failure_is_non_fatal():
    transport = BleTransport("DD:67:E2:1E:C0:93")
    transport._client = MagicMock()
    transport._has_uuid = MagicMock(return_value=True)

    class _FailClient:
        async def write_gatt_char(self, uuid, data):
            raise BleakError("gatt fail")

    asyncio.run(transport._set_current_time(_FailClient()))  # must not raise
