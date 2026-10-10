import asyncio
import uuid

from helpers import client_for, make_settings, running_server
from voxstream.core.session import Session
from voxstream.engines.mock import MockEngine

LONG = "Esta es una oración de prueba bastante larga para generar audio. " * 25


async def test_session_buffers_stay_bounded_with_stalled_sink():
    settings = make_settings(audio_queue_frames=8)
    gate = asyncio.Event()

    async def stalled(_: bytes) -> None:
        await gate.wait()

    s = Session(uuid.uuid4(), MockEngine(), "mock_es", settings, stalled)
    s.start()
    feeder = asyncio.create_task(s.feed(LONG[:1500]))
    max_audio = max_seg = 0
    for _ in range(30):
        await asyncio.sleep(0.01)
        max_audio = max(max_audio, s.audio_queue.qsize())
        max_seg = max(max_seg, s.segment_queue.qsize())
    assert max_audio <= 8 and max_seg <= 4
    assert not feeder.done(), "feed must block (backpressure) while the sink is stalled"
    gate.set()
    await asyncio.wait_for(feeder, 5)
    await s.end()
    result = await asyncio.wait_for(s.wait(), 10)
    assert result.state == "COMPLETED"


async def test_stalled_client_does_not_grow_server_buffers():
    async with (
        running_server(MockEngine(), audio_queue_frames=8) as server,
        client_for(server) as c,
    ):
        await c.start()
        for i in range(0, 1800, 300):
            await c.text(LONG[i : i + 300])
        await asyncio.sleep(0.5)  # the client never reads
        (conn,) = server._conns
        assert conn.session is not None
        assert conn.session.audio_queue.qsize() <= 8
        assert conn.session.segment_queue.qsize() <= 4
        await c.cancel()
