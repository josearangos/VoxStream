import time

import pytest

from helpers import client_for, running_server
from voxstream.config import Settings
from voxstream.engines.kokoro.engine import KokoroEngine

pytestmark = pytest.mark.model

LONG = "Esta es una frase de prueba bastante larga para medir la cancelación del audio. " * 3


async def test_audio_stops_within_500ms_of_cancel():
    settings = Settings(_env_file=None, port=0, allow_unverified_voices=True)
    async with running_server(
        KokoroEngine(settings), allow_unverified_voices=True, engine="kokoro"
    ) as server:
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
            print(f"cancel latency: {latency_ms:.0f} ms")
            assert latency_ms < 500
