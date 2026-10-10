import asyncio

from websockets.asyncio.client import connect

from helpers import client_for, running_server
from voxstream.engines.mock import MockEngine


async def test_disconnect_cancels_and_releases_slot():
    engine = MockEngine(delay_s=0.05)
    async with running_server(engine) as server:
        before = len(asyncio.all_tasks())
        async with client_for(server) as c:
            await c.start()
            await c.text("Una frase larga para sintetizar. " * 20)
            await asyncio.sleep(0.1)
            assert server.admission.active == 1
        for _ in range(100):
            if server.admission.active == 0:
                break
            await asyncio.sleep(0.02)
        assert server.admission.active == 0
        await asyncio.sleep(0.1)
        # a new request is accepted immediately, from a new connection
        async with client_for(server) as c2:
            assert (await c2.start())["type"] == "started"
            await c2.cancel()
            await c2.collect()
        await asyncio.sleep(0.2)
        assert len(asyncio.all_tasks()) <= before + 2  # no leaked pipeline tasks


async def test_abrupt_close_without_handshake():
    async with running_server(MockEngine(delay_s=0.05)) as server:
        ws = await connect(f"ws://127.0.0.1:{server.port}/v1/stream")
        from helpers import Client

        c = Client(ws)
        await c.start()
        await c.text("Texto. " * 50)
        ws.transport.abort()
        for _ in range(100):
            if server.admission.active == 0:
                break
            await asyncio.sleep(0.02)
        assert server.admission.active == 0
