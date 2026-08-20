"""BLE transport for the visomat comfort soft BT via `bleak`.

The device (comfort soft BT, Blood Pressure Service 0x1810) only accepts
connections during its sync window and terminates them after a few seconds.
This transport therefore exposes a lean connect/subscribe/close interface and
lets the caller (listener) handle reconnects. GATT services are resolved with
`get_services()` right after connecting, and notifications on 0x2A35
(blood pressure) and 0x2A19 (battery) are forwarded to callbacks.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Self

from bleak import BleakClient
from bleak.exc import BleakError

from .protocol import (
    BATTERY_LEVEL_UUID,
    BLOOD_PRESSURE_FEATURE_UUID,
    BLOOD_PRESSURE_MEASUREMENT_UUID,
    CURRENT_TIME_UUID,
)

LOGGER = logging.getLogger("visomat_bt.transport")

NotificationHandler = Callable[[bytes], Awaitable[None] | None]


@dataclass(frozen=True)
class DeviceInfo:
    """Identity data collected from the GAP + Device Information services."""

    name: str = ""
    manufacturer: str = ""
    model: str = ""
    serial: str = ""
    firmware: str = ""
    hardware: str = ""
    battery: int | None = None
    feature: int | None = None


class BleTransport:
    """Thin wrapper around a single BleakClient connection."""

    def __init__(self, address: str, timeout: float = 15.0) -> None:
        self.address = address
        self.timeout = timeout
        self._client: BleakClient | None = None
        self._on_measurement: NotificationHandler | None = None
        self._on_battery: NotificationHandler | None = None
        self._disconnected: asyncio.Event | None = None

    @property
    def connected(self) -> bool:
        return self._client is not None and self._client.is_connected

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        await self.close()

    async def connect(
        self,
        on_measurement: NotificationHandler,
        on_battery: NotificationHandler | None = None,
    ) -> DeviceInfo:
        """Connect, resolve services and start notifications.

        Raises bleak.exc.BleakError on failure so the listener can retry.
        A hard timeout guards against devices that connect but never resolve
        their GATT database (the visomat only does so during an active sync).
        """
        self._on_measurement = on_measurement
        self._on_battery = on_battery
        self._disconnected = asyncio.Event()

        client = BleakClient(self.address, timeout=self.timeout, disconnected_callback=self._on_disconnect)
        try:
            await client.connect(dangerous_use_bleak_cache=True)
        except TypeError:
            # Older bleak versions do not support the cache kwarg.
            await client.connect()
        self._client = client

        try:
            async with asyncio.timeout(self.timeout):
                await client.start_notify(BLOOD_PRESSURE_MEASUREMENT_UUID, self._measurement_handler)
                if on_battery is not None and self._has_uuid(BATTERY_LEVEL_UUID):
                    try:
                        await client.start_notify(BATTERY_LEVEL_UUID, self._battery_handler)
                    except (BleakError, TimeoutError) as exc:
                        # The visomat does not reliably support notifications on
                        # the battery characteristic. This must never abort the
                        # session — the blood pressure notifications are the hot
                        # path and may arrive within the same short sync window.
                        LOGGER.debug("battery notify not available: %s", exc)
                await self._set_current_time(client)
                return await self._read_device_info(client)
        except (TimeoutError, BleakError):
            await self.close()
            raise

    async def _read_device_info(self, client: BleakClient) -> DeviceInfo:
        info = DeviceInfo(name=client.address)
        # Characteristic reads are not part of the hot path; a failed read must
        # never break the connection.
        for uuid, attr in (
            ("00002a00-0000-1000-8000-00805f9b34fb", "name"),  # GAP Device Name
            ("00002a29-0000-1000-8000-00805f9b34fb", "manufacturer"),
            ("00002a24-0000-1000-8000-00805f9b34fb", "model"),
            ("00002a25-0000-1000-8000-00805f9b34fb", "serial"),
            ("00002a26-0000-1000-8000-00805f9b34fb", "firmware"),
            ("00002a27-0000-1000-8000-00805f9b34fb", "hardware"),
        ):
            if self._has_uuid(uuid):
                value = await self._read_text(client, uuid)
                if value:
                    info = _setattr(info, attr, value)
        if self._has_uuid(BATTERY_LEVEL_UUID):
            value = await self._read_u8(client, BATTERY_LEVEL_UUID)
            info = _setattr(info, "battery", value)
        if self._has_uuid(BLOOD_PRESSURE_FEATURE_UUID):
            value = await self._read_u16(client, BLOOD_PRESSURE_FEATURE_UUID)
            info = _setattr(info, "feature", value)
        return info

    async def _set_current_time(self, client: BleakClient) -> None:
        """Set the device clock via the Current Time Service (0x2A2B).

        The visomat's internal clock resets when the battery is removed, which
        corrupts the measurement timestamps. Writing the current local time on
        every (successful) connect keeps the clock in sync. Never fatal.
        """
        if not self._has_uuid(CURRENT_TIME_UUID):
            return
        now = datetime.now().astimezone().timetuple()
        payload = bytes(
            [
                now.tm_year & 0xFF,
                (now.tm_year >> 8) & 0xFF,
                now.tm_mon,
                now.tm_mday,
                now.tm_hour,
                now.tm_min,
                now.tm_sec,
                now.tm_wday + 1,  # DayOfWeek: Monday=1 ... Sunday=7
                0,  # fractions256
                0,  # adjust_reason: manual
            ]
        )
        try:
            await client.write_gatt_char(CURRENT_TIME_UUID, payload)
            LOGGER.info("device clock set to %s", datetime.now().astimezone().isoformat(timespec="seconds"))
        except (BleakError, TimeoutError) as exc:
            LOGGER.debug("could not set device clock: %s", exc)

    def _has_uuid(self, uuid: str) -> bool:
        if self._client is None:
            return False
        return self._client.services.get_characteristic(uuid) is not None

    async def _read_text(self, client: BleakClient, uuid: str) -> str:
        try:
            data = await client.read_gatt_char(uuid)
            return bytes(data).decode("utf-8", errors="replace").strip()
        except (BleakError, TimeoutError, OSError) as exc:
            LOGGER.debug("read %s failed: %s", uuid, exc)
            return ""

    async def _read_u8(self, client: BleakClient, uuid: str) -> int | None:
        try:
            data = await client.read_gatt_char(uuid)
            return int.from_bytes(bytes(data)[:1], "little")
        except (BleakError, TimeoutError, OSError) as exc:
            LOGGER.debug("read %s failed: %s", uuid, exc)
            return None

    async def _read_u16(self, client: BleakClient, uuid: str) -> int | None:
        try:
            data = await client.read_gatt_char(uuid)
            return int.from_bytes(bytes(data)[:2], "little")
        except (BleakError, TimeoutError, OSError) as exc:
            LOGGER.debug("read %s failed: %s", uuid, exc)
            return None

    def _measurement_handler(self, _client, data: bytearray) -> None:
        self._dispatch(self._on_measurement, data)

    def _battery_handler(self, _client, data: bytearray) -> None:
        self._dispatch(self._on_battery, data)

    def _dispatch(self, handler: NotificationHandler | None, data: bytearray) -> None:
        if handler is None:
            return
        result = handler(bytes(data))
        if asyncio.iscoroutine(result):
            asyncio.create_task(result)

    def _on_disconnect(self, _client) -> None:
        if self._disconnected is not None:
            self._disconnected.set()

    async def wait_disconnected(self, timeout: float | None = None) -> None:
        """Wait until the device terminates the connection (its normal behaviour)."""
        if self._disconnected is not None:
            await asyncio.wait_for(self._disconnected.wait(), timeout)

    async def close(self) -> None:
        client = self._client
        self._client = None
        if client is not None and client.is_connected:
            try:
                await client.disconnect()
            except BleakError:
                pass


def _setattr(info: DeviceInfo, attr: str, value) -> DeviceInfo:
    """Return a copy of `info` with `attr` set to `value`."""
    return DeviceInfo(
        name=value if attr == "name" else info.name,
        manufacturer=value if attr == "manufacturer" else info.manufacturer,
        model=value if attr == "model" else info.model,
        serial=value if attr == "serial" else info.serial,
        firmware=value if attr == "firmware" else info.firmware,
        hardware=value if attr == "hardware" else info.hardware,
        battery=value if attr == "battery" else info.battery,
        feature=value if attr == "feature" else info.feature,
    )
