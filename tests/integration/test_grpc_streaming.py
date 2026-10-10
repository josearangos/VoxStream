import asyncio
import time

import grpc
import pytest
from grpc import aio

from helpers import SPANISH_PIECES, client_for, running_server
from voxstream.engines.mock import MockEngine


async def test_audio_arrives_before_last_piece_sent():
    async with running_server(MockEngine(delay_s=0.01)) as server:
        server.transport = "grpc"
        async with client_for(server) as c:
            await c.start()
            first_audio: list[float] = []

            async def reader():
                while True:
                    m = await c.recv(10)
                    if isinstance(m, bytes):
                        first_audio.append(time.monotonic())
                    elif '"completed"' in m:
                        return

            task = asyncio.create_task(reader())
            for piece in SPANISH_PIECES:
                await c.text(piece)
                await asyncio.sleep(0.05)
            last_sent = time.monotonic()
            await c.end()
            await task
            assert first_audio and first_audio[0] < last_sent  # SC-003


async def test_default_voice_used_and_reported():
    async with running_server(MockEngine(voices=["a", "b"]), default_voice="b") as server:
        server.transport = "grpc"
        async with client_for(server) as c:
            started = await c.start()
            assert started["stream"]["voice"] == "b"
            await c.cancel()
            await c.collect()


async def test_same_audio_and_descriptor_as_websocket():
    results = {}
    async with running_server(MockEngine()) as server:
        for transport in ("websocket", "grpc"):
            server.transport = transport
            async with client_for(server) as c:
                started = await c.start(voice="mock_es")
                for piece in SPANISH_PIECES:
                    await c.text(piece)
                await c.end()
                frames, controls = await c.collect(timeout=30)
                results[transport] = (
                    started["stream"],
                    b"".join(f.payload for f in frames),
                    [f.sequence for f in frames],
                    controls[-1],
                )
    ws, grpc_ = results["websocket"], results["grpc"]
    assert ws[0] == grpc_[0]  # Started descriptors equal field by field
    assert ws[1] == grpc_[1] and len(ws[1]) > 0  # SC-002: identical PCM bytes
    assert ws[2] == grpc_[2]
    assert ws[3]["audio_frames"] == grpc_[3]["audio_frames"]
    assert ws[3]["chars"] == grpc_[3]["chars"]


async def test_oversize_text_fails_call_with_resource_exhausted():
    async with running_server(MockEngine()) as server:
        server.transport = "grpc"
        async with client_for(server) as c:
            await c.start()
            await c.text("x" * (64 * 1024 + 1))
            with pytest.raises(aio.AioRpcError) as exc:
                await c.recv(10)
            assert exc.value.code() == grpc.StatusCode.RESOURCE_EXHAUSTED
        for _ in range(100):
            if server.admission.active == 0:
                break
            await asyncio.sleep(0.02)
        assert server.admission.active == 0
