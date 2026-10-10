import asyncio
import json
import socket
import urllib.error
import urllib.request

import grpc
import pytest
from grpc import aio
from websockets.asyncio.client import connect

from helpers import client_for, make_settings, running_server
from voxstream.app import VoxStreamApp
from voxstream.engines.mock import MockEngine
from voxstream.transports.grpc.gen import voxstream_pb2 as pb
from voxstream.transports.grpc.gen import voxstream_pb2_grpc as pb_grpc


def http_get(port: int, path: str) -> tuple[int, str]:
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}{path}", timeout=5) as r:
            return r.status, r.read().decode()
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode()


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


async def test_websocket_disabled_grpc_works_and_health_stays_on_port():
    async with running_server(MockEngine(), enable_websocket=False) as server:
        with pytest.raises(Exception):  # noqa: B017 - 404 on the health listener, no upgrade
            async with connect(f"ws://127.0.0.1:{server.port}/v1/stream"):
                pass
        server.transport = "grpc"
        async with client_for(server) as c:
            assert (await c.start())["type"] == "started"
            await c.cancel()
            await c.collect()
        assert (await asyncio.to_thread(http_get, server.port, "/healthz"))[0] == 200
        status, body = await asyncio.to_thread(http_get, server.port, "/readyz")
        assert status == 200 and json.loads(body)["ready"] is True
        assert (await asyncio.to_thread(http_get, server.port, "/nope"))[0] == 404


async def test_readyz_body_identical_with_and_without_websocket():
    bodies = []
    for enabled in (True, False):
        async with running_server(MockEngine(), enable_websocket=enabled) as server:
            status, body = await asyncio.to_thread(http_get, server.port, "/readyz")
            assert status == 200
            bodies.append(body)
    assert bodies[0] == bodies[1]


async def test_grpc_disabled_connection_fails_and_websocket_works():
    async with running_server(MockEngine(), enable_grpc=False) as server:
        async with client_for(server) as c:
            assert (await c.start())["type"] == "started"
            await c.cancel()
            await c.collect()
        assert (await asyncio.to_thread(http_get, server.port, "/healthz"))[0] == 200
        async with aio.insecure_channel(f"127.0.0.1:{free_port()}") as ch:
            stub = pb_grpc.SynthesizerStub(ch)
            with pytest.raises(aio.AioRpcError) as exc:
                await stub.GetCapabilities(pb.CapabilitiesRequest(), timeout=2)
            assert exc.value.code() in (
                grpc.StatusCode.UNAVAILABLE,
                grpc.StatusCode.DEADLINE_EXCEEDED,
            )


async def test_both_disabled_is_a_configuration_error():
    app = VoxStreamApp(make_settings(enable_websocket=False, enable_grpc=False), MockEngine())
    with pytest.raises(ValueError) as exc:
        await app.start()
    assert "VOXSTREAM_ENABLE_WEBSOCKET" in str(exc.value)
    assert "VOXSTREAM_ENABLE_GRPC" in str(exc.value)


async def test_health_listener_survives_garbage_and_slow_clients():
    async with running_server(MockEngine(), enable_websocket=False) as server:
        reader, writer = await asyncio.open_connection("127.0.0.1", server.port)
        writer.write(b"POST /healthz HTTP/1.1\r\n\r\n")
        await writer.drain()
        assert b"405" in await asyncio.wait_for(reader.read(100), 5)
        writer.close()
        reader, writer = await asyncio.open_connection("127.0.0.1", server.port)
        writer.write(b"\x00\xff" * 4000 + b"\r\n\r\n")
        await writer.drain()
        await asyncio.wait_for(reader.read(100), 5)
        writer.close()
        assert (await asyncio.to_thread(http_get, server.port, "/healthz"))[0] == 200
