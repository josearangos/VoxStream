from collections.abc import AsyncIterator

import pytest_asyncio

from helpers import running_server
from voxstream.engines.mock import MockEngine


@pytest_asyncio.fixture
async def service_url() -> AsyncIterator[str]:
    async with running_server(MockEngine(delay_s=0.01)) as server:
        yield f"ws://127.0.0.1:{server.port}/v1/stream"


@pytest_asyncio.fixture
async def short_limit_url() -> AsyncIterator[str]:
    async with running_server(MockEngine(), max_text_chars=10) as server:
        yield f"ws://127.0.0.1:{server.port}/v1/stream"
