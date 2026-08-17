"""Entry point for the visomat comfort soft BT BLE gateway service."""

from __future__ import annotations

import argparse
import asyncio
import logging
import signal

from .config import load_config
from .listener import Listener
from .protocol import BloodPressureMeasurement
from .publisher import Publisher
from .transport import DeviceInfo

LOGGER = logging.getLogger("visomat_bt.main")


async def amain(cfg) -> None:
    loop = asyncio.get_running_loop()
    publisher = Publisher(cfg.mqtt)
    listener = Listener(cfg)
    publisher.start()

    async def on_measurement(measurement: BloodPressureMeasurement) -> None:
        await publisher.publish_measurement(measurement)

    async def on_battery(level: int) -> None:
        await publisher.publish_battery(level)

    async def on_metadata(info: DeviceInfo) -> None:
        await publisher.publish_metadata(info)

    listener.set_handlers(on_measurement, on_battery, on_metadata)

    stop = asyncio.Event()

    def request_stop() -> None:
        stop.set()

    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, request_stop)

    try:
        task = asyncio.create_task(listener.run())
        await stop.wait()
        await listener.stop()
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
    finally:
        publisher.stop()


def main() -> None:
    parser = argparse.ArgumentParser(description="visomat comfort soft BT BLE gateway")
    parser.add_argument("-c", "--config", default="config.yaml", help="path to config file")
    parser.add_argument("-v", "--verbose", action="store_true", help="enable debug logging")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
    )
    cfg = load_config(args.config)
    try:
        asyncio.run(amain(cfg))
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
