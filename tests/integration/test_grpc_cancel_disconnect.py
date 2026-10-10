import asyncio
import gc
import time

import grpc

from helpers import client_for, running_server
from voxstream.engines.mock import MockEngine

LONG = "Esta es una oración larga de prueba para el audio. " * 12


async def wait_idle(server, timeout=5.0):
    deadline = time.monotonic() + timeout
    while server.admission.active and time.monotonic() < deadline:
        await asyncio.sleep(0.02)
    return server.admission.active == 0


async def test_cancel_stops_audio_within_500ms_and_yields_one_cancelled():
    async with running_server(MockEngine(delay_s=0.02)) as server:
        server.transport = "grpc"
        async with client_for(server) as c:
            await c.start()
            await c.text(LONG)
            while not isinstance(await c.recv(30), bytes):
                pass
            t_cancel = time.monotonic()
            await c.cancel()
            last_frame = t_cancel
            controls = []
            while True:
                m = await c.recv(10)
                if isinstance(m, bytes):
                    last_frame = time.monotonic()
                    continue
                controls.append(m)
                break
            assert '"cancelled"' in controls[0]
            assert last_frame - t_cancel < 0.5
            await asyncio.sleep(0.3)
            assert c.inbox.empty(), "nothing may follow the terminal event"
            assert await wait_idle(server)


async def test_cancel_racing_completion_never_both_terminals():
    async with running_server(MockEngine()) as server:
        server.transport = "grpc"
        async with client_for(server) as c:
            await c.start()
            await c.text("Hola.")
            await c.end()
            await c.cancel()
            _, controls = await c.collect()
            terminals = [m for m in controls if m["type"] in ("completed", "cancelled")]
            assert len(terminals) == 1


async def test_call_cancel_releases_slot_without_leaks():
    async with running_server(MockEngine(delay_s=0.05)) as server:
        server.transport = "grpc"
        gc.collect()
        before = len(asyncio.all_tasks())
        async with client_for(server) as c:
            await c.start()
            await c.text(LONG)
            await asyncio.sleep(0.1)
            assert server.admission.active == 1
            c.call.cancel()
            assert await wait_idle(server)
        async with client_for(server) as c2:  # a new request succeeds immediately
            assert (await c2.start())["type"] == "started"
            await c2.cancel()
            await c2.collect()
        await asyncio.sleep(0.3)
        assert server.admission.active == 0
        assert len(asyncio.all_tasks()) <= before + 4  # no leaked pipeline tasks


async def test_dropping_the_channel_releases_slot():
    async with running_server(MockEngine(delay_s=0.05)) as server:
        server.transport = "grpc"
        async with client_for(server) as c:
            await c.start()
            await c.text(LONG)
            await asyncio.sleep(0.1)
            assert server.admission.active == 1
            await c.channel.close(grace=None)
        assert await wait_idle(server)
        assert grpc.StatusCode.OK  # sanity: module in use
