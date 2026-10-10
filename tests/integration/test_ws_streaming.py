import asyncio
import time

from helpers import SPANISH_PIECES, client_for, running_server
from voxstream.engines.mock import MockEngine


async def test_audio_arrives_before_last_piece_sent():
    engine = MockEngine(delay_s=0.01)
    async with running_server(engine) as server, client_for(server) as c:
        await c.start()
        first_audio: list[float] = []

        async def reader():
            frames = 0
            while True:
                m = await c.recv(10)
                if isinstance(m, bytes):
                    frames += 1
                    if not first_audio:
                        first_audio.append(time.monotonic())
                elif '"completed"' in m:
                    return frames

        task = asyncio.create_task(reader())
        pieces = [
            "Hola, ¿cómo estás hoy? ",
            "Me alegra verte. ",
            "Hoy hace un día muy ",
            "bonito. Y ",
            "mañana también.",
        ]
        for p in pieces:
            await c.text(p)
            await asyncio.sleep(0.15)
        last_sent = time.monotonic()
        await c.end()
        frames = await task
        assert frames > 0
        assert first_audio and first_audio[0] < last_sent  # SC-010


async def test_streamed_and_single_piece_speak_same_text():
    text = "".join(SPANISH_PIECES)
    spoken = []
    for pieces in ([text], SPANISH_PIECES):
        engine = MockEngine()
        async with running_server(engine) as server, client_for(server) as c:
            await c.start()
            for p in pieces:
                await c.text(p)
            await c.end()
            await c.collect()
        spoken.append(" ".join(engine.synthesized))
    assert spoken[0] == spoken[1] == " ".join(text.split())
