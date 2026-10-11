import asyncio
import json
import re

import pytest

from helpers import client_for, make_settings
from voxstream.app import VoxStreamApp
from voxstream.engines.base import EngineUnavailableError, OutOfMemoryError
from voxstream.engines.mock import MockEngine

LEAK = re.compile(r"(/Users/|/home/|Traceback|\.py\b|File \")")


def check(err, code, category, retryable, with_id=None):
    assert err["type"] == "error"
    assert err["code"] == code and err["category"] == category
    assert err["retryable"] is retryable
    assert not LEAK.search(err["message"])
    if with_id is True:
        assert err["request_id"]
    if with_id is False:
        assert err["request_id"] is None


async def test_no_active_request(serve):
    async with serve() as server, client_for(server) as c:
        for payload in (
            {"type": "text", "request_id": "x", "text": "a"},
            {"type": "end", "request_id": "x"},
            {"type": "cancel", "request_id": "x"},
        ):
            await c.send(**payload)
            check(await c.recv_json(), "NO_ACTIVE_REQUEST", "protocol", False)


async def test_request_mismatch(serve):
    async with serve() as server, client_for(server) as c:
        await c.start()
        await c.send(type="text", request_id="other", text="hola")
        check(await c.recv_json(), "REQUEST_MISMATCH", "protocol", False)
        await c.send(type="cancel", request_id="other")
        check(await c.recv_json(), "REQUEST_MISMATCH", "protocol", False)
        await c.cancel()
        await c.collect()


async def test_busy_second_start_on_same_connection(serve):
    async with serve() as server, client_for(server) as c:
        await c.start()
        await c.send(type="start")
        check(await c.recv_json(), "BUSY", "capacity", True)
        await c.text("Hola mundo.")  # the active stream is unaffected
        await c.end()
        _, controls = await c.collect(timeout=60)
        assert controls[-1]["type"] == "completed"


async def test_busy_from_second_connection(serve):
    async with serve() as server, client_for(server) as c1, client_for(server) as c2:
        await c1.start()
        await c2.send(type="start")
        check(await c2.recv_json(), "BUSY", "capacity", True, with_id=False)
        await c1.text("Hola.")
        await c1.end()
        _, controls = await c1.collect(timeout=60)
        assert controls[-1]["type"] == "completed"
        assert (await c2.start())["type"] == "started"  # slot released
        await c2.cancel()
        await c2.collect()


async def test_unsupported_language(serve):
    async with serve() as server, client_for(server) as c:
        await c.send(type="start", language="en")
        check(await c.recv_json(), "UNSUPPORTED_LANGUAGE", "validation", False, with_id=False)
        assert server.admission.active == 0


async def test_unsupported_voice_lists_available(serve):
    async with serve() as server, client_for(server) as c:
        await c.send(type="start", voice="nope")
        err = await c.recv_json()
        check(err, "UNSUPPORTED_VOICE", "validation", False, with_id=False)
        voices = server.engine.capabilities().voices
        assert all(v in err["message"] for v in voices)


async def test_unsupported_engine(serve):
    async with serve() as server, client_for(server) as c:
        await c.send(type="start", engine="no-such-engine")
        check(await c.recv_json(), "UNSUPPORTED_ENGINE", "validation", False, with_id=False)


async def test_empty_request(serve):
    async with serve() as server, client_for(server) as c:
        await c.start()
        await c.text("   ")
        await c.end()
        _, controls = await c.collect()
        check(controls[-1], "EMPTY_REQUEST", "validation", False, with_id=True)
        assert server.admission.active == 0


async def test_text_after_end_does_not_stop_request(serve):
    async with serve() as server, client_for(server) as c:
        await c.start()
        await c.text("Hola mundo.")
        await c.end()
        await c.text("más")
        errors = []
        frames_seen = False
        while True:
            m = await c.recv(60)
            if isinstance(m, bytes):
                frames_seen = True
                continue
            d = json.loads(m)
            if d["type"] == "error":
                errors.append(d)
            if d["type"] == "completed":
                break
        assert frames_seen
        assert errors and errors[0]["code"] == "NO_ACTIVE_REQUEST"


async def test_idle_timeout_speaks_pending_segments_first(serve):
    async with serve(idle_timeout_s=0.4) as server, client_for(server) as c:
        await c.start()
        await c.text("Primera frase completa. Y una incompleta")
        frames, controls = await c.collect(timeout=30)
        assert frames, "the complete sentence is spoken before the timeout error"
        check(controls[-1], "IDLE_TIMEOUT", "timeout", True, with_id=True)
        assert server.admission.active == 0


async def test_request_timeout(serve):
    async with serve(request_timeout_s=0.5, idle_timeout_s=30) as server, client_for(server) as c:
        await c.start()
        await c.text("Hola.")
        await asyncio.sleep(0.6)
        _, controls = await c.collect()
        check(controls[-1], "REQUEST_TIMEOUT", "timeout", True, with_id=True)


# -- engine-specific failures: mock engine only ---------------------------------------------


class UnavailableEngine(MockEngine):
    async def start(self) -> None:
        raise EngineUnavailableError("/secret/path/model.onnx could not be opened")


async def run_with_engine(engine, **settings):
    server = VoxStreamApp(make_settings(**settings), engine)
    await server.start()
    return server


@pytest.mark.parametrize(
    "engine,code,category,retryable",
    [
        (MockEngine(fail_at_segment=0), "ENGINE_FAILURE", "engine", False),
        (
            MockEngine(fail_at_segment=0, fail_with=OutOfMemoryError("x")),
            "OUT_OF_MEMORY",
            "engine",
            False,
        ),
        (MockEngine(fail_at_segment=0, fail_with=MemoryError()), "OUT_OF_MEMORY", "engine", False),
        (
            MockEngine(fail_at_segment=0, fail_with=ValueError("/etc/x.py")),
            "INTERNAL_ERROR",
            "internal",
            False,
        ),
    ],
)
async def test_engine_failures_end_request_with_one_error(engine, code, category, retryable):
    server = await run_with_engine(engine)
    try:
        async with client_for(server) as c:
            await c.start()
            await c.text("Hola mundo.")
            await c.end()
            _, controls = await c.collect()
            check(controls[-1], code, category, retryable, with_id=True)
            assert not [m for m in controls if m["type"] == "completed"]
            assert server.admission.active == 0
    finally:
        await server.close()


async def test_engine_unavailable_rejects_start():
    server = await run_with_engine(UnavailableEngine())
    try:
        async with client_for(server) as c:
            await c.send(type="start")
            err = await c.recv_json()
            check(err, "ENGINE_UNAVAILABLE", "engine", False, with_id=False)
            assert server.admission.active == 0
    finally:
        await server.close()


async def test_no_verified_voice_rejects_start_with_engine_unavailable():
    server = await run_with_engine(MockEngine(voices=[]))
    try:
        async with client_for(server) as c:
            await c.send(type="start")
            check(await c.recv_json(), "ENGINE_UNAVAILABLE", "engine", False, with_id=False)
    finally:
        await server.close()
