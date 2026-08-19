"""Entry point for the visomat → Garmin Connect sync service."""

from __future__ import annotations

import argparse
import asyncio
import logging
import signal

from .config import load_config
from .syncer import Syncer

LOGGER = logging.getLogger("garmin_sync.main")


async def run_syncer(cfg, stop: asyncio.Event | None = None) -> None:
    """Run the Garmin sync (MQTT listener + uploader) until ``stop`` is set.

    Exposed separately so a supervising entrypoint (e.g. the Home Assistant
    add-on) can run it concurrently with the visomat BLE gateway. Returns
    immediately when the sync is disabled.
    """
    if not cfg.enabled:
        LOGGER.info("garmin_sync deaktiviert (garmin_sync.enabled: false), beende")
        return

    syncer = Syncer(cfg)
    syncer.login()
    syncer.start()

    try:
        if stop is None:
            stop = asyncio.Event()
            loop = asyncio.get_running_loop()

            def request_stop() -> None:
                stop.set()

            for sig in (signal.SIGINT, signal.SIGTERM):
                loop.add_signal_handler(sig, request_stop)
        await stop.wait()
    finally:
        syncer.stop()


async def amain(cfg, login_only: bool = False) -> None:
    syncer = Syncer(cfg)

    if login_only:
        syncer.login_interactive()
        LOGGER.info("Login abgeschlossen, Tokens gespeichert")
        return

    await run_syncer(cfg)


def main() -> None:
    parser = argparse.ArgumentParser(description="visomat → Garmin Connect sync")
    parser.add_argument("-c", "--config", default="config.yaml", help="path to config file")
    parser.add_argument("-v", "--verbose", action="store_true", help="enable debug logging")
    parser.add_argument("--login", action="store_true", help="einmaligen (interaktiven) Garmin-Login ausführen")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
    )
    cfg = load_config(args.config)
    try:
        asyncio.run(amain(cfg, login_only=args.login))
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
