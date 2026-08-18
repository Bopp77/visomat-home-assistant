"""Tests for the garmin_sync entrypoint behaviour."""

import asyncio

from garmin_sync.config import Config
from garmin_sync.main import amain


class _DisabledConfig(Config):
    enabled = False


def test_amain_returns_cleanly_when_disabled():
    async def run():
        await amain(_DisabledConfig(), login_only=False)

    asyncio.run(run())  # must not raise / must not attempt login
