import asyncio

from contract.test_errors import check
from helpers import client_for, running_server
from voxstream.engines.mock import MockEngine


async def test_idle_timeout_speaks_pending_segments_first():
    async with running_server(MockEngine(), idle_timeout_s=0.4) as server:
        server.transport = "grpc"
        async with client_for(server) as c:
            await c.start()
            await c.text("Primera frase completa. Y una incompleta")
            frames, controls = await c.collect(timeout=30)
            assert frames
            check(controls[-1], "IDLE_TIMEOUT", "timeout", True, with_id=True)
            assert server.admission.active == 0


async def test_request_timeout():
    async with running_server(MockEngine(), request_timeout_s=0.5, idle_timeout_s=30) as server:
        server.transport = "grpc"
        async with client_for(server) as c:
            await c.start()
            await c.text("Hola.")
            await asyncio.sleep(0.6)
            _, controls = await c.collect()
            check(controls[-1], "REQUEST_TIMEOUT", "timeout", True, with_id=True)


async def test_text_too_long_mid_stream():
    async with running_server(MockEngine(), max_text_chars=50) as server:
        server.transport = "grpc"
        async with client_for(server) as c:
            await c.start()
            await c.text("Hola mundo. ")
            await c.text("x" * 80)
            _, controls = await c.collect()
            check(controls[-1], "TEXT_TOO_LONG", "validation", False, with_id=True)
            assert server.admission.active == 0


async def test_end_with_no_text_is_empty_request():
    async with running_server(MockEngine()) as server:
        server.transport = "grpc"
        async with client_for(server) as c:
            await c.start()
            await c.end()
            _, controls = await c.collect()
            check(controls[-1], "EMPTY_REQUEST", "validation", False, with_id=True)


async def test_engine_failure_at_segment_n():
    async with running_server(MockEngine(fail_at_segment=1)) as server:
        server.transport = "grpc"
        async with client_for(server) as c:
            await c.start()
            await c.text("Primera frase. Segunda frase. Tercera frase.")
            await c.end()
            frames, controls = await c.collect()
            check(controls[-1], "ENGINE_FAILURE", "engine", False, with_id=True)
            assert not [m for m in controls if m["type"] == "completed"]
            assert server.admission.active == 0
