"""Unified entrypoint for the Home Assistant add-on.

Runs the visomat BLE gateway and — when ``garmin_sync.enabled`` is set — the
Garmin sync service in a single process. Configuration is read from the
Supervisor-provided ``/data/options.json`` (falling back to ``config.yaml``),
so the add-on needs no local config file.

Each service is supervised individually: if one fails (e.g. a Garmin login
error before the MFA login was completed), it is restarted with a short
backoff while the other keeps running.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import signal

from garmin_sync.config import load_config as load_garmin_config
from garmin_sync.main import run_syncer
from visomat_bt.config import load_config as load_visomat_config
from visomat_bt.main import run_gateway

LOGGER = logging.getLogger("visomat_addon")

HA_OPTIONS_PATH = "/data/options.json"


def _ha_log_level(default: str = "info") -> str:
    """Read the ``log_level`` option from the Supervisor options file."""
    try:
        with open(HA_OPTIONS_PATH, encoding="utf-8") as handle:
            raw = json.load(handle) or {}
        level = raw.get("log_level") or default
    except (OSError, ValueError):
        return default
    return level if level in ("debug", "info", "warning", "error") else default


async def _supervise(run, stop: asyncio.Event, service: str, base_delay: float = 5.0) -> None:
    """Run ``run(stop)`` and restart it with backoff if it fails."""
    retries = 0
    while not stop.is_set():
        try:
            await run(stop)
            return
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001 - supervision must never die
            retries += 1
            delay = min(30, base_delay * retries)
            LOGGER.error("%s failed (%s), restart in %ss", service, exc, delay)
            try:
                await asyncio.wait_for(stop.wait(), delay)
            except TimeoutError:
                pass


async def amain(visomat_cfg, garmin_cfg, stop: asyncio.Event) -> None:
    tasks = [
        asyncio.create_task(
            _supervise(lambda s: run_gateway(visomat_cfg, s), stop, "visomat gateway"),
            name="gateway",
        ),
        asyncio.create_task(
            _supervise(lambda s: run_syncer(garmin_cfg, s), stop, "garmin sync"),
            name="garmin",
        ),
    ]
    await stop.wait()
    for task in tasks:
        task.cancel()
    await asyncio.gather(*tasks, return_exceptions=True)


def main() -> None:
    parser = argparse.ArgumentParser(description="visomat Home Assistant add-on entrypoint")
    parser.add_argument("-c", "--config", default="config.yaml", help="path to config file (fallback)")
    parser.add_argument("-v", "--verbose", action="store_true", help="enable debug logging")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else getattr(logging, _ha_log_level().upper(), logging.INFO),
        format="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
    )
    visomat_cfg = load_visomat_config(args.config)
    garmin_cfg = load_garmin_config(args.config)
    stop = asyncio.Event()

    def request_stop() -> None:
        stop.set()

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, request_stop)
        except NotImplementedError:
            pass
    try:
        loop.run_until_complete(amain(visomat_cfg, garmin_cfg, stop))
    finally:
        loop.close()


if __name__ == "__main__":
    main()
