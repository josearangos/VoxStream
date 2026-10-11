import asyncio

import pytest

from helpers import client_for, running_server
from voxstream.engines.mock import MockEngine

TEXT = "Primera frase corta. Segunda frase corta. Tercera frase corta."


@pytest.mark.parametrize("failing,next_", [("websocket", "grpc"), ("grpc", "websocket")])
async def test_engine_failure_on_one_transport_leaves_the_other_usable(failing, next_):
    engine = MockEngine(fail_at_segment=1)
    async with running_server(engine) as app:
        app.transport = failing
        async with client_for(app) as a:
            await a.start()
            await a.text(TEXT)
            await a.end()
            _, controls = await a.collect()
            assert controls[-1]["type"] == "error"
            assert controls[-1]["code"] == "ENGINE_FAILURE"
        for _ in range(100):
            if app.admission.active == 0:
                break
            await asyncio.sleep(0.02)
        assert app.admission.active == 0

        app.transport = next_
        async with client_for(app) as b:
            await b.start()
            await b.text("Hola.")
            await b.end()
            frames, controls = await b.collect()
            assert controls[-1]["type"] == "completed"
            assert frames and frames[-1].last
