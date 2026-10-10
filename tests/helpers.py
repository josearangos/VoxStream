"""Shared test helpers: a running server and a thin protocol client."""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

from websockets.asyncio.client import ClientConnection, connect

from voxstream.config import Settings
from voxstream.engines.base import TTSEngine
from voxstream.transports.websocket.framing import AudioFrame, decode_frame
from voxstream.transports.websocket.server import VoxStreamServer

SPANISH_PIECES = [
    "Hola, ",
    "¿cómo est",
    "ás hoy? Me ale",
    "gra verte. Hoy hace ",
    "un día muy bonito en la ciudad.",
]


def make_settings(**kw: Any) -> Settings:
    kw.setdefault("port", 0)
    kw.setdefault("engine", "mock")
    return Settings(_env_file=None, **kw)


@asynccontextmanager
async def running_server(tts: TTSEngine, **settings_kw: Any) -> AsyncIterator[VoxStreamServer]:
    settings = make_settings(**settings_kw)
    async with VoxStreamServer(settings, tts) as server:
        yield server


class Client:
    def __init__(self, ws: ClientConnection) -> None:
        self.ws = ws
        self.request_id: str | None = None
        self.stream: dict[str, Any] | None = None

    async def send(self, **payload: Any) -> None:
        await self.ws.send(json.dumps(payload))

    async def recv(self, timeout: float = 5) -> str | bytes:
        return await asyncio.wait_for(self.ws.recv(), timeout)

    async def recv_json(self, timeout: float = 5) -> dict[str, Any]:
        while True:
            m = await self.recv(timeout)
            if isinstance(m, str):
                return json.loads(m)

    async def start(self, **kw: Any) -> dict[str, Any]:
        await self.send(type="start", **kw)
        reply = await self.recv_json()
        if reply["type"] == "started":
            self.request_id = reply["request_id"]
            self.stream = reply["stream"]
        return reply

    async def text(self, text: str) -> None:
        await self.send(type="text", request_id=self.request_id, text=text)

    async def end(self) -> None:
        await self.send(type="end", request_id=self.request_id)

    async def cancel(self) -> None:
        await self.send(type="cancel", request_id=self.request_id)

    async def collect(self, timeout: float = 10) -> tuple[list[AudioFrame], list[dict[str, Any]]]:
        """Read until a terminal message; return (frames, control messages)."""
        frames: list[AudioFrame] = []
        controls: list[dict[str, Any]] = []
        while True:
            m = await self.recv(timeout)
            if isinstance(m, bytes):
                frames.append(decode_frame(m))
                continue
            d = json.loads(m)
            controls.append(d)
            if d["type"] in ("completed", "cancelled") or (
                d["type"] == "error" and d.get("request_id")
            ):
                return frames, controls


@asynccontextmanager
async def client_for(server: VoxStreamServer) -> AsyncIterator[Client]:
    async with connect(f"ws://127.0.0.1:{server.port}/v1/stream", close_timeout=1) as ws:
        yield Client(ws)
