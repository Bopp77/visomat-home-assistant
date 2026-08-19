"""Tests for the unified add-on entrypoint."""

import asyncio
from dataclasses import dataclass

from garmin_sync.config import Config as GarminConfig
from visomat_addon.main import _supervise, amain
from visomat_bt.config import Config as VisomatConfig


@dataclass
class _FakeMqttConfig:
    host: str = "localhost"
    port: int = 1883
    username: str | None = None
    password: str | None = None
    base_topic: str = "visomat_bt"
    discovery_prefix: str = "homeassistant"


@dataclass
class _FakeBleConfig:
    mac: str = ""
    name: str = "comfort soft"
    adapter: str = "hci0"
    scan_timeout_sec: float = 1.0
    scan_interval_sec: float = 1.0
    reconnect_delay_sec: float = 0.01
    timeout_sec: float = 1.0


def _visomat_config() -> VisomatConfig:
    cfg = VisomatConfig()
    cfg.ble = _FakeBleConfig()
    cfg.mqtt = _FakeMqttConfig()
    return cfg


def _garmin_config(enabled: bool = True) -> GarminConfig:
    cfg = GarminConfig()
    cfg.enabled = enabled
    return cfg


async def _run_with_stop(visomat_cfg, garmin_cfg, delay=0.05):
    stop = asyncio.Event()
    task = asyncio.create_task(amain(visomat_cfg, garmin_cfg, stop))
    await asyncio.sleep(delay)
    stop.set()
    await task


def test_amain_stops_cleanly_with_garmin_disabled():
    asyncio.run(_run_with_stop(_visomat_config(), _garmin_config(enabled=False)))


def test_amain_stops_cleanly_with_garmin_enabled():
    asyncio.run(_run_with_stop(_visomat_config(), _garmin_config(enabled=True)))


def test_supervise_restarts_failing_service():
    attempts = 0

    async def run(_stop):
        nonlocal attempts
        attempts += 1
        raise RuntimeError("boom")

    async def scenario():
        stop = asyncio.Event()
        task = asyncio.create_task(_supervise(run, stop, "test service", base_delay=0.01))
        await asyncio.sleep(0.05)  # let a few failures + backoff run
        stop.set()
        await task
        return attempts

    count = asyncio.run(scenario())  # must not raise despite repeated failures
    assert count >= 2

