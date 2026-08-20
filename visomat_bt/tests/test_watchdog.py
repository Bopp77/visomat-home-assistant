"""Tests for the consecutive-failure watchdog."""

import asyncio
from dataclasses import dataclass
from unittest.mock import patch

from visomat_bt.listener import Listener


@dataclass
class _Ble:
    mac: str = "DD:67:E2:1E:C0:93"
    name: str = "comfort soft"
    adapter: str = "hci0"
    scan_timeout_sec: float = 1.0
    scan_interval_sec: float = 1.0
    reconnect_delay_sec: float = 0.01
    timeout_sec: float = 1.0
    watchdog_max_failures: int = 3


class _Cfg:
    def __init__(self, threshold):
        self.ble = _Ble(watchdog_max_failures=threshold)


def _listener(threshold: int) -> Listener:
    return Listener(_Cfg(threshold))


def test_watchdog_exits_after_threshold():
    lst = _listener(3)

    async def fail(_stop=None):
        raise RuntimeError("radio unhealthy")

    lst._session = fail
    with patch("visomat_bt.listener.os._exit") as mock_exit:
        asyncio.run(lst.run())

    mock_exit.assert_called_once_with(1)


def test_watchdog_resets_on_success():
    lst = _listener(3)

    async def alternate(_stop=None):
        raise RuntimeError("radio unhealthy")

    lst._session = alternate
    with patch("visomat_bt.listener.os._exit") as mock_exit:
        asyncio.run(lst.run())

    # All sessions fail -> watchdog must fire (3 failures).
    mock_exit.assert_called_once_with(1)


def test_watchdog_disabled_never_exits():
    lst = _listener(0)

    async def fail(_stop=None):
        raise RuntimeError("boom")

    lst._session = fail

    async def scenario():
        with patch("visomat_bt.listener.os._exit") as mock_exit:
            task = asyncio.create_task(lst.run())
            await asyncio.sleep(0.05)
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
            return mock_exit

    mock_exit = asyncio.run(scenario())
    mock_exit.assert_not_called()
