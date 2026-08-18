"""Entry point for the visomat → Garmin Connect sync service."""

from __future__ import annotations

import argparse
import asyncio
import logging
import signal

from .config import load_config
from .syncer import Syncer

LOGGER = logging.getLogger("garmin_sync.main")


async def amain(cfg, login_only: bool = False) -> None:
    syncer = Syncer(cfg)

    if login_only:
        syncer.login_interactive()
        LOGGER.info("Login abgeschlossen, Tokens gespeichert")
        return

    if not cfg.enabled:
        LOGGER.info("garmin_sync deaktiviert (garmin_sync.enabled: false), beende")
        return

    syncer.login()
    syncer.start()

    stop = asyncio.Event()

    def request_stop() -> None:
        stop.set()

    for sig in (signal.SIGINT, signal.SIGTERM):
        loop = asyncio.get_running_loop()
        loop.add_signal_handler(sig, request_stop)

    try:
        await stop.wait()
    finally:
        syncer.stop()


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
