import asyncio

import pytest
from demo.stream_client import (
    AudioChunk,
    Completed,
    ServiceError,
    ServiceUnreachable,
    Started,
    stream_speech,
)

from helpers import client_for, running_server
from voxstream.engines.mock import MockEngine

TEXT = "Hola, ¿cómo estás hoy? Me alegra verte."


async def test_event_order_and_duration(service_url: str) -> None:
    events = [e async for e in stream_speech(service_url, TEXT)]
    assert isinstance(events[0], Started) and events[0].sample_rate == 24000
    assert isinstance(events[-1], Completed)
    chunks = [e for e in events if isinstance(e, AudioChunk)]
    assert chunks
    assert abs(sum(c.ms for c in chunks) - events[-1].audio_ms) <= 100


async def test_unreachable() -> None:
    with pytest.raises(ServiceUnreachable):
        async for _ in stream_speech("ws://127.0.0.1:1/v1/stream", TEXT):
            pass


async def test_cancel_frees_slot() -> None:
    async with running_server(MockEngine(delay_s=0.05)) as server:
        url = f"ws://127.0.0.1:{server.port}/v1/stream"
        gen = stream_speech(url, TEXT * 5)
        async for event in gen:
            if isinstance(event, AudioChunk):
                break
        await gen.aclose()
        await asyncio.sleep(0.2)
        async with client_for(server) as c:
            assert (await c.start())["type"] == "started"


async def test_busy_surfaces() -> None:
    async with running_server(MockEngine(delay_s=0.05)) as server:
        url = f"ws://127.0.0.1:{server.port}/v1/stream"
        async with client_for(server) as c:
            assert (await c.start())["type"] == "started"
            events = [e async for e in stream_speech(url, TEXT)]
        assert events == [ServiceError("BUSY")]


async def test_text_too_long(short_limit_url: str) -> None:
    events = [e async for e in stream_speech(short_limit_url, TEXT)]
    assert ServiceError("TEXT_TOO_LONG") in events
