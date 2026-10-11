"""Shared test helpers: a running server and a thin protocol client."""

from __future__ import annotations

import asyncio
import json
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

import grpc
from grpc import aio
from websockets.asyncio.client import ClientConnection, connect

from voxstream.app import VoxStreamApp
from voxstream.config import Settings
from voxstream.engines.base import TTSEngine
from voxstream.transports.grpc.gen import voxstream_pb2 as pb
from voxstream.transports.grpc.gen import voxstream_pb2_grpc as pb_grpc
from voxstream.transports.websocket.framing import AudioFrame, decode_frame, encode_frame

SPANISH_PIECES = [
    "Hola, ",
    "¿cómo est",
    "ás hoy? Me ale",
    "gra verte. Hoy hace ",
    "un día muy bonito en la ciudad.",
]


def make_settings(**kw: Any) -> Settings:
    kw.setdefault("port", 0)
    kw.setdefault("grpc_port", 0)
    kw.setdefault("engine", "mock")
    return Settings(_env_file=None, **kw)


@asynccontextmanager
async def running_server(tts: TTSEngine, **settings_kw: Any) -> AsyncIterator[VoxStreamApp]:
    settings = make_settings(**settings_kw)
    async with VoxStreamApp(settings, tts) as server:
        yield server


class _ClientBase:
    """Methods shared by the WebSocket and gRPC test clients."""

    request_id: str | None = None
    stream: dict[str, Any] | None = None

    async def send(self, **payload: Any) -> None:
        raise NotImplementedError

    async def recv(self, timeout: float = 5) -> str | bytes:
        raise NotImplementedError

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


class Client(_ClientBase):
    """WebSocket client."""

    def __init__(self, ws: ClientConnection) -> None:
        self.ws = ws

    async def send(self, **payload: Any) -> None:
        await self.ws.send(json.dumps(payload))

    async def recv(self, timeout: float = 5) -> str | bytes:
        return await asyncio.wait_for(self.ws.recv(), timeout)


def _opt(**kw: Any) -> dict[str, Any]:
    return {k: v for k, v in kw.items() if v is not None}


def _control(ev: pb.ServerEvent) -> dict[str, Any] | None:
    """Normalize a control event to the dict the WebSocket protocol would carry."""
    case = ev.WhichOneof("event")
    if case == "started":
        d = ev.started.stream
        return {
            "type": "started",
            "request_id": ev.started.request_id,
            "stream": {
                "encoding": d.encoding,
                "sample_rate": d.sample_rate,
                "channels": d.channels,
                "frame_ms": d.frame_ms,
                "voice": d.voice,
                "engine": d.engine,
                "language": d.language,
                "streaming_mode": d.streaming_mode,
                "execution_provider": d.execution_provider,
            },
        }
    if case == "completed":
        c = ev.completed
        return {
            "type": "completed",
            "request_id": c.request_id,
            "audio_frames": c.audio_frames,
            "audio_ms": c.audio_ms,
            "chars": c.chars,
            "timing": dict(c.timing),
        }
    if case == "cancelled":
        return {
            "type": "cancelled",
            "request_id": ev.cancelled.request_id,
            "audio_frames_sent": ev.cancelled.audio_frames_sent,
        }
    if case == "error":
        e = ev.error
        return {
            "type": "error",
            "request_id": e.request_id if e.HasField("request_id") else None,
            "code": e.code,
            "category": e.category,
            "message": e.message,
            "retryable": e.retryable,
        }
    return None


class GrpcClient(_ClientBase):
    """gRPC client with the WebSocket client's API (one request per call; ``start`` reopens)."""

    def __init__(self, channel: aio.Channel) -> None:
        self.channel = channel
        self.stub = pb_grpc.SynthesizerStub(channel)  # type: ignore[no-untyped-call]
        self.inbox: asyncio.Queue[str | bytes | BaseException] = asyncio.Queue()
        self.outbound: asyncio.Queue[pb.ClientEvent | None] | None = None
        self.call: Any = None
        self.pump: asyncio.Task[None] | None = None
        self.terminal_seen = False

    async def _requests(self, q: asyncio.Queue[pb.ClientEvent | None]) -> AsyncIterator[Any]:
        while (ev := await q.get()) is not None:
            yield ev

    async def _pump(self, call: Any) -> None:
        try:
            async for ev in call:
                if ev.WhichOneof("event") == "audio":
                    a = ev.audio
                    self.inbox.put_nowait(
                        encode_frame(uuid.UUID(a.request_id), a.sequence, a.pcm, last=a.last)
                    )
                else:
                    ctl = _control(ev)
                    assert ctl is not None
                    if ctl["type"] != "started" and (ctl["type"] != "error" or ctl["request_id"]):
                        self.terminal_seen = True
                    self.inbox.put_nowait(json.dumps(ctl))
        except aio.AioRpcError as exc:
            # Writes racing the end of a finished call fail the client side; not a server fault.
            if exc.code() != grpc.StatusCode.CANCELLED and not self.terminal_seen:
                self.inbox.put_nowait(exc)

    async def _open(self) -> None:
        await self._close_call()
        self.outbound = asyncio.Queue()
        self.terminal_seen = False
        self.call = self.stub.Stream(self._requests(self.outbound))
        self.pump = asyncio.create_task(self._pump(self.call))

    async def _close_call(self) -> None:
        if self.outbound is not None:
            self.outbound.put_nowait(None)
        if self.call is not None:
            self.call.cancel()
        if self.pump is not None:
            await asyncio.gather(self.pump, return_exceptions=True)
        self.call = self.pump = self.outbound = None

    async def _call_finished(self) -> bool:
        if self.pump is None:
            return True
        await asyncio.wait({self.pump}, timeout=0.05)
        return self.pump.done()

    async def send(self, **payload: Any) -> None:
        kind = payload.pop("type")
        if kind == "capabilities":
            caps = await self.stub.GetCapabilities(pb.CapabilitiesRequest())
            self.inbox.put_nowait(
                json.dumps(
                    {
                        "type": "capabilities",
                        "engine": caps.engine,
                        "version": caps.version,
                        "languages": list(caps.languages),
                        "voices": list(caps.voices),
                        "audio_format": {
                            "encoding": caps.encoding,
                            "sample_rate": caps.sample_rate,
                            "channels": caps.channels,
                        },
                        "streaming_mode": caps.streaming_mode,
                        "supports_cancel": caps.supports_cancel,
                        "execution_provider": caps.execution_provider,
                        "memory_notes": caps.memory_notes,
                    }
                )
            )
            return
        rid = payload.get("request_id")
        ev: pb.ClientEvent
        if kind == "start":
            ev = pb.ClientEvent(start=pb.Start(**_opt(**payload)))
            if await self._call_finished():
                await self._open()
        elif kind == "text":
            ev = pb.ClientEvent(text=pb.Text(text=payload["text"], **_opt(request_id=rid)))
        elif kind == "end":
            ev = pb.ClientEvent(end=pb.End(**_opt(request_id=rid)))
        elif kind == "cancel":
            ev = pb.ClientEvent(cancel=pb.Cancel(**_opt(request_id=rid)))
        else:
            raise ValueError(f"unknown message type {kind!r}")
        if self.pump is None:
            await self._open()  # input before any start still reaches the server
        if (
            self.outbound is not None
            and not self.terminal_seen
            and not (self.pump and self.pump.done())
        ):
            self.outbound.put_nowait(ev)  # events for a finished call are dropped

    async def send_raw(self, ev: pb.ClientEvent) -> None:
        """Write a protobuf event as is (opens a call if none is active)."""
        if await self._call_finished():
            await self._open()
        assert self.outbound is not None
        self.outbound.put_nowait(ev)

    async def recv(self, timeout: float = 5) -> str | bytes:
        item = await asyncio.wait_for(self.inbox.get(), timeout)
        if isinstance(item, BaseException):
            raise item
        return item

    async def close(self) -> None:
        await self._close_call()
        await self.channel.close()


@asynccontextmanager
async def client_for(server: VoxStreamApp) -> AsyncIterator[Any]:
    if getattr(server, "transport", "websocket") == "grpc":
        channel = aio.insecure_channel(
            f"127.0.0.1:{server.grpc_port}",
            options=[("grpc.enable_http_proxy", 0)],
        )
        gc = GrpcClient(channel)
        try:
            yield gc
        finally:
            await gc.close()
        return
    async with connect(f"ws://127.0.0.1:{server.port}/v1/stream", close_timeout=1) as ws:
        yield Client(ws)


class FakeVibeBackend:
    """Stands in for the torch runtime: deterministic float audio, honors the stop hook."""

    device = "cpu"
    sample_rate = 24000

    def __init__(
        self,
        *,
        delay_s: float = 0.0,
        ms_per_char: int = 40,
        block_ms: int = 200,
        fail_with: BaseException | None = None,
    ) -> None:
        self.delay_s = delay_s
        self.ms_per_char = ms_per_char
        self.block_ms = block_ms
        self.fail_with = fail_with
        self.loaded = False
        self.closed = 0
        self.stop_seen = False
        self.produced = 0

    def load(self) -> None:
        self.loaded = True

    def stream(self, text: str, voice: str, should_stop: Any) -> Any:
        import time

        import numpy as np

        if self.fail_with is not None:
            raise self.fail_with
        total = self.sample_rate * self.ms_per_char * len(text) // 1000
        per_block = self.sample_rate * self.block_ms // 1000
        wave = (np.sin(2 * np.pi * 220 * np.arange(total) / self.sample_rate) * 0.1).astype(
            np.float32
        )
        finished = False
        try:
            for off in range(0, total, per_block):
                if should_stop():
                    return
                if self.delay_s:
                    time.sleep(self.delay_s)
                self.produced += 1
                yield wave[off : off + per_block]
            finished = True
        finally:
            # Like the torch backend, an early close or a stop request ends generation.
            self.stop_seen = not finished

    def close(self) -> None:
        self.closed += 1


def make_vibevoice_stub(**kw: Any) -> Any:
    """A real ``VibeVoiceEngine`` over the fake backend, with every candidate voice exposed."""
    from voxstream.engines.vibevoice.engine import VibeVoiceEngine

    settings = make_settings(engine="vibevoice", allow_unverified_voices=True)
    return VibeVoiceEngine(settings, backend=FakeVibeBackend(**kw))
