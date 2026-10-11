"""Real VibeVoice model; excluded by default (needs the 'vibevoice' extra and downloaded files)."""

import pytest

from helpers import client_for, running_server
from voxstream.config import Settings
from voxstream.engines.vibevoice.engine import VibeVoiceEngine

pytestmark = pytest.mark.model


async def test_streams_one_spanish_sentence():
    settings = Settings(_env_file=None, engine="vibevoice", enable_grpc=False, port=0)
    engine = VibeVoiceEngine(settings)
    ok, reason, _ = engine.readiness()
    if not ok:
        pytest.skip(reason or "VibeVoice is not ready")
    await engine.start()  # the lazy model load takes longer than the client's start timeout
    async with running_server(engine, engine="vibevoice", enable_grpc=False) as server:
        async with client_for(server) as c:
            started = await c.start()
            assert started["stream"]["engine"] == "vibevoice"
            await c.text("Hola, esto es una prueba.")
            await c.end()
            frames, controls = await c.collect(timeout=120)
    assert frames, "no audio frame arrived"
    assert controls[-1]["type"] == "completed"
