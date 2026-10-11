import time

import pytest

from helpers import client_for, running_server
from voxstream.config import Settings
from voxstream.engines.kokoro.engine import KokoroEngine

pytestmark = pytest.mark.model

LONG = "Esta es una frase de prueba bastante larga para medir la cancelación del audio. " * 3


CASES = [
    ("kokoro", "websocket"),
    ("kokoro", "grpc"),
    ("vibevoice", "websocket"),  # WebSocket only (plan.md)
]


def build(engine_name: str):
    settings = Settings(_env_file=None, port=0, engine=engine_name, allow_unverified_voices=True)
    if engine_name == "vibevoice":
        from voxstream.engines.vibevoice.engine import VibeVoiceEngine

        return VibeVoiceEngine(settings)
    return KokoroEngine(settings)


@pytest.mark.parametrize("engine_name,transport", CASES)
async def test_audio_stops_within_500ms_of_cancel(engine_name, transport):
    engine = build(engine_name)
    if engine_name == "vibevoice":
        await engine.start()  # keep the slow model load out of the client's start timeout
    async with running_server(
        engine,
        allow_unverified_voices=True,
        engine=engine_name,
        enable_grpc=transport == "grpc",
    ) as server:
        server.transport = transport
        async with client_for(server) as c:
            await c.start()
            await c.text(LONG)
            while not isinstance(await c.recv(60), bytes):
                pass
            t_cancel = time.monotonic()
            await c.cancel()
            last_frame = t_cancel
            while True:
                m = await c.recv(30)
                if isinstance(m, bytes):
                    last_frame = time.monotonic()
                elif '"cancelled"' in m:
                    break
            latency_ms = (last_frame - t_cancel) * 1000
            print(f"{engine_name} {transport} cancel latency: {latency_ms:.0f} ms")
            assert latency_ms < 500
