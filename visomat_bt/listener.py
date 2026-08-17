"""Connection supervision for the visomat BLE gateway.

The device only accepts connections during its sync window and terminates
them itself after a short time. This listener therefore runs a persistent
loop: scan for the device, connect, subscribe to notifications, then wait
for the connection to drop and reconnect immediately. Every received
measurement is handed to the publisher; device metadata and the battery
level are refreshed on each (re)connect.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable

from bleak import BleakScanner
from bleak.backends.device import BLEDevice

from .protocol import (
    BloodPressureMeasurement,
    ProtocolError,
    parse_measurement,
)
from .transport import BleTransport, DeviceInfo

LOGGER = logging.getLogger("visomat_bt.listener")

MeasurementHandler = Callable[[BloodPressureMeasurement], Awaitable[None]]
BatteryHandler = Callable[[int], Awaitable[None]]
MetadataHandler = Callable[[DeviceInfo], Awaitable[None]]


class Listener:
    """Coordinates BLE discovery, connect and reconnects."""

    def __init__(self, cfg) -> None:
        self._cfg = cfg
        self._name_pattern = (cfg.ble.name or "comfort soft").lower()
        self._on_measurement: MeasurementHandler | None = None
        self._on_battery: BatteryHandler | None = None
        self._on_metadata: MetadataHandler | None = None
        self._stop = asyncio.Event()
        self._connected = False

    def set_handlers(
        self,
        on_measurement: MeasurementHandler,
        on_battery: BatteryHandler,
        on_metadata: MetadataHandler,
    ) -> None:
        self._on_measurement = on_measurement
        self._on_battery = on_battery
        self._on_metadata = on_metadata

    async def run(self) -> None:
        while not self._stop.is_set():
            try:
                await self._session()
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                LOGGER.warning("session failed: %s", exc or type(exc).__name__, exc_info=exc is not None)
                self._set_connected(False)
            await self._wait_or_stop(self._cfg.ble.reconnect_delay_sec)

    async def _session(self) -> None:
        # Continuous scan: the visomat only advertises during its short sync
        # window, so a periodic scan-with-gaps misses it. A persistent scanner
        # with detection callback connects the instant the device appears.
        device = await self._scan_until_found()
        if device is None:
            return
        transport = BleTransport(device.address, timeout=self._cfg.ble.timeout_sec)
        async with transport:
            info = await transport.connect(
                handle_notification(self._on_measurement),
                self._on_battery if self._on_battery is not None else None,
            )
            self._set_connected(True)
            if self._on_metadata is not None:
                await self._on_metadata(info)
            LOGGER.info("connected to %s (%s)", info.name or device.address, device.address)
            await transport.wait_disconnected(timeout=None)
        self._set_connected(False)
        LOGGER.info("disconnected by device, reconnecting")

    async def _scan_until_found(self) -> BLEDevice | None:
        found = asyncio.Event()
        result: list[BLEDevice] = []

        def on_detected(device: BLEDevice, _advertisement_data) -> None:
            if found.is_set():
                return
            address_match = self._cfg.ble.mac and device.address.lower() == self._cfg.ble.mac.lower()
            name_match = not self._cfg.ble.mac and device.name and self._name_pattern in device.name.lower()
            if address_match or name_match:
                result.append(device)
                found.set()

        scanner = BleakScanner(detection_callback=on_detected, scanning_mode="active")
        try:
            await scanner.start()
        except Exception as exc:  # noqa: BLE001 - scanning must never kill the loop
            LOGGER.debug("scanner start failed: %s", exc)
            return None
        try:
            await found.wait()
        finally:
            await scanner.stop()
        return result[0] if result else None

    async def _wait_or_stop(self, delay: float) -> None:
        try:
            await asyncio.wait_for(self._stop.wait(), delay)
        except TimeoutError:
            pass

    def _set_connected(self, connected: bool) -> None:
        if connected != self._connected:
            self._connected = connected
            LOGGER.info("connection state: %s", "online" if connected else "offline")

    async def stop(self) -> None:
        self._stop.set()


def handle_notification(handler: MeasurementHandler) -> Callable[[bytes], Awaitable[None]]:
    """Wrap a raw 0x2A35 payload into a parsed measurement dispatch."""

    async def wrapped(data: bytes) -> None:
        try:
            measurement = parse_measurement(data)
        except ProtocolError as exc:
            LOGGER.warning("dropped unparsable measurement (%d bytes): %s", len(data), exc)
            return
        await handler(measurement)

    return wrapped
