"""Contract fixtures: ``engine_name`` runs every contract test against each engine (SC-008)."""

from __future__ import annotations

from collections.abc import AsyncIterator, Callable
from contextlib import AbstractAsyncContextManager, asynccontextmanager
from typing import Any

import pytest

from helpers import running_server
from voxstream.engines.base import TTSEngine
from voxstream.engines.mock import MockEngine
from voxstream.transports.websocket.server import VoxStreamServer


@pytest.fixture(params=["mock", pytest.param("kokoro", marks=pytest.mark.model)])
def engine_name(request: pytest.FixtureRequest) -> str:
    return str(request.param)


def build_engine(name: str, **mock_kw: Any) -> TTSEngine:
    if name == "mock":
        return MockEngine(**mock_kw)
    from voxstream.config import Settings
    from voxstream.engines.registry import create_engine

    return create_engine(name, Settings(_env_file=None, engine=name))


@pytest.fixture
def serve(engine_name: str) -> Callable[..., AbstractAsyncContextManager[VoxStreamServer]]:
    """``async with serve(**settings) as server`` -- mock options apply to the mock engine only."""

    @asynccontextmanager
    async def _serve(
        mock: dict[str, Any] | None = None, **settings: Any
    ) -> AsyncIterator[VoxStreamServer]:
        engine = build_engine(engine_name, **(mock or {}))
        async with running_server(engine, engine=engine_name, **settings) as server:
            yield server

    return _serve
