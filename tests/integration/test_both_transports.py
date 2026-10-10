import asyncio

import pytest

from helpers import client_for, make_settings, running_server
from voxstream.app import VoxStreamApp
from voxstream.engines.mock import MockEngine


class CountingEngine(MockEngine):
    starts = 0
    stops = 0

    async def start(self) -> None:
        type(self).starts += 1
        await super().start()

    async def stop(self) -> None:
        type(self).stops += 1
        await super().stop()


def test_default_settings_enable_both():
    s = make_settings()
    assert s.enable_websocket is True and s.enable_grpc is True


@pytest.mark.parametrize("holder,other", [("websocket", "grpc"), ("grpc", "websocket")])
async def test_limit_is_shared_across_transports(holder, other):
    async with running_server(MockEngine(delay_s=0.02)) as server:
        server.transport = holder
        async with client_for(server) as a:
            await a.start()
            await a.text("Una frase larga para mantener la solicitud activa. " * 5)
            server.transport = other
            async with client_for(server) as b:
                await b.send(type="start")
                err = await b.recv_json()
                assert err["code"] == "BUSY" and err["request_id"] is None
            await a.cancel()
            await a.collect()
        for _ in range(100):
            if server.admission.active == 0:
                break
            await asyncio.sleep(0.02)
        server.transport = other
        async with client_for(server) as b:  # slot released: the other transport now succeeds
            assert (await b.start())["type"] == "started"
            await b.cancel()
            await b.collect()


async def test_one_engine_started_once_and_stopped_once():
    CountingEngine.starts = CountingEngine.stops = 0
    app = VoxStreamApp(make_settings(), CountingEngine())
    async with app:
        for transport in ("websocket", "grpc", "websocket"):
            app.transport = transport
            async with client_for(app) as c:
                await c.start()
                await c.cancel()
                await c.collect()
            for _ in range(100):
                if app.admission.active == 0:
                    break
                await asyncio.sleep(0.02)
        assert CountingEngine.starts == 1
    assert CountingEngine.stops == 1
