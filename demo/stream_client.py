"""Async client of WebSocket protocol v1: yields typed events, cancels on close."""

from __future__ import annotations

import asyncio
import contextlib
import json
from collections.abc import AsyncIterator
from dataclasses import dataclass

from websockets.asyncio.client import connect
from websockets.exceptions import WebSocketException

HEADER_SIZE = 21
CLOSE_TIMEOUT_S = 1.0


class ServiceUnreachable(Exception):
    """Cannot connect to, or lost the connection with, the service."""


class UnsupportedStream(Exception):
    """The service announced an audio encoding the demo cannot play."""


@dataclass(frozen=True)
class Started:
    request_id: str
    sample_rate: int
    channels: int


@dataclass(frozen=True)
class AudioChunk:
    payload: bytes
    ms: float


@dataclass(frozen=True)
class Completed:
    audio_ms: float


@dataclass(frozen=True)
class ServiceError:
    code: str


Event = Started | AudioChunk | Completed | ServiceError


async def stream_speech(url: str, text: str) -> AsyncIterator[Event]:
    """Speak ``text`` through the service; closing the generator cancels the request."""
    try:
        ws = await connect(url, close_timeout=CLOSE_TIMEOUT_S, max_size=None)
    except (OSError, WebSocketException, TimeoutError) as exc:
        raise ServiceUnreachable(url) from exc

    request_id: str | None = None
    terminal = False
    try:
        try:
            await ws.send(json.dumps({"type": "start"}))
            sample_rate, channels = 24000, 1
            async for message in ws:
                if isinstance(message, bytes):
                    payload = message[HEADER_SIZE:]
                    if payload:
                        ms = len(payload) / (2 * channels * sample_rate) * 1000
                        yield AudioChunk(payload, ms)
                    continue
                msg = json.loads(message)
                kind = msg.get("type")
                if kind == "started":
                    stream = msg["stream"]
                    if stream.get("encoding") != "pcm_s16le":
                        raise UnsupportedStream(str(stream.get("encoding")))
                    request_id = msg["request_id"]
                    sample_rate = int(stream["sample_rate"])
                    channels = int(stream["channels"])
                    yield Started(request_id or "", sample_rate, channels)
                    await ws.send(
                        json.dumps({"type": "text", "request_id": request_id, "text": text})
                    )
                    await ws.send(json.dumps({"type": "end", "request_id": request_id}))
                elif kind == "completed":
                    terminal = True
                    yield Completed(float(msg.get("audio_ms", 0)))
                    return
                elif kind == "cancelled":
                    terminal = True
                    return
                elif kind == "error":
                    if request_id and not msg.get("request_id"):
                        continue  # protocol-level error (e.g. our pipelined `end` after the
                        # request already failed); the request's own terminal error follows
                    terminal = True
                    yield ServiceError(str(msg.get("code", "")))
                    return
            raise ServiceUnreachable(url)
        except WebSocketException as exc:
            raise ServiceUnreachable(url) from exc
    finally:
        # Stop, page disconnect or error: free the service slot, never leave the socket open.
        with contextlib.suppress(Exception):
            if request_id and not terminal:
                await asyncio.wait_for(
                    ws.send(json.dumps({"type": "cancel", "request_id": request_id})),
                    CLOSE_TIMEOUT_S,
                )
        with contextlib.suppress(Exception):
            await asyncio.wait_for(ws.close(), CLOSE_TIMEOUT_S)
