"""Contract fixtures: ``engine_name`` runs every contract test against each engine (SC-008)."""

from __future__ import annotations

from collections.abc import AsyncIterator, Callable
from contextlib import AbstractAsyncContextManager, asynccontextmanager
from typing import Any

import pytest

from helpers import running_server
from voxstream.app import VoxStreamApp
from voxstream.engines.base import TTSEngine
from voxstream.engines.mock import MockEngine


@pytest.fixture(params=["mock", "vibevoice", pytest.param("kokoro", marks=pytest.mark.model)])
def engine_name(request: pytest.FixtureRequest) -> str:
    return str(request.param)


def build_engine(name: str, **mock_kw: Any) -> TTSEngine:
    if name == "mock":
        return MockEngine(**mock_kw)
    if name == "vibevoice":
        from helpers import make_vibevoice_stub

        return make_vibevoice_stub(**{k: v for k, v in mock_kw.items() if k == "delay_s"})
    from voxstream.config import Settings
    from voxstream.engines.registry import create_engine

    return create_engine(name, Settings(_env_file=None, engine=name))


@pytest.fixture(params=["websocket", "grpc"])
def transport(request: pytest.FixtureRequest) -> str:
    return str(request.param)


@pytest.fixture
def serve(
    engine_name: str, transport: str
) -> Callable[..., AbstractAsyncContextManager[VoxStreamApp]]:
    """``async with serve(**settings) as server`` -- mock options apply to the mock engine only."""

    @asynccontextmanager
    async def _serve(
        mock: dict[str, Any] | None = None, **settings: Any
    ) -> AsyncIterator[VoxStreamApp]:
        if engine_name == "vibevoice":
            if transport == "grpc":
                pytest.skip("vibevoice is WebSocket-only (plan.md, constitution III exception)")
            settings.setdefault("enable_grpc", False)
        engine = build_engine(engine_name, **(mock or {}))
        async with running_server(engine, engine=engine_name, **settings) as server:
            server.transport = transport
            yield server

    return _serve
