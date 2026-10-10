import asyncio

import grpc

from contract.test_errors import check
from helpers import client_for, running_server
from voxstream.engines.mock import MockEngine
from voxstream.transports.grpc.gen import voxstream_pb2 as pb


async def test_event_with_no_case_is_malformed_and_call_stays_usable():
    async with running_server(MockEngine()) as server:
        server.transport = "grpc"
        async with client_for(server) as c:
            await c.send_raw(pb.ClientEvent())
            check(await c.recv_json(), "MALFORMED_MESSAGE", "protocol", False, with_id=False)
            assert (await c.start())["type"] == "started"
            await c.cancel()
            await c.collect()


async def test_events_before_start_are_no_active_request():
    async with running_server(MockEngine()) as server:
        server.transport = "grpc"
        async with client_for(server) as c:
            for ev in (
                pb.ClientEvent(text=pb.Text(text="a")),
                pb.ClientEvent(end=pb.End()),
                pb.ClientEvent(cancel=pb.Cancel()),
            ):
                await c.send_raw(ev)
                check(await c.recv_json(), "NO_ACTIVE_REQUEST", "protocol", False)


async def test_request_id_mismatch_keeps_request_running():
    async with running_server(MockEngine()) as server:
        server.transport = "grpc"
        async with client_for(server) as c:
            await c.start()
            await c.send(type="end", request_id="other")
            check(await c.recv_json(), "REQUEST_MISMATCH", "protocol", False)
            await c.text("Hola mundo.")
            await c.end()
            _, controls = await c.collect()
            assert controls[-1]["type"] == "completed"


async def test_text_after_end_errors_but_request_completes():
    async with running_server(MockEngine()) as server:
        server.transport = "grpc"
        async with client_for(server) as c:
            await c.start()
            await c.text("Hola mundo.")
            await c.end()
            await c.text("más")
            _, controls = await c.collect()
            codes = [m["code"] for m in controls if m["type"] == "error"]
            assert codes == ["NO_ACTIVE_REQUEST"]
            assert controls[-1]["type"] == "completed"


async def test_second_end_is_ignored_and_request_completes_once():
    async with running_server(MockEngine()) as server:
        server.transport = "grpc"
        async with client_for(server) as c:
            await c.start()
            await c.text("Hola mundo.")
            await c.end()
            await c.end()
            _, controls = await c.collect()
            assert [m["type"] for m in controls].count("completed") == 1
            assert not [m for m in controls if m["type"] == "error"]


async def test_second_start_is_busy_and_first_request_unaffected():
    async with running_server(MockEngine()) as server:
        server.transport = "grpc"
        async with client_for(server) as c:
            await c.start()
            await c.send(type="start")
            check(await c.recv_json(), "BUSY", "capacity", True)
            await c.text("Hola.")
            await c.end()
            _, controls = await c.collect()
            assert controls[-1]["type"] == "completed"


async def test_rejected_start_returns_error_without_request_id_and_call_ends_ok():
    async with running_server(MockEngine()) as server:
        server.transport = "grpc"
        for kw, code in (
            ({"voice": "nope"}, "UNSUPPORTED_VOICE"),
            ({"language": "en"}, "UNSUPPORTED_LANGUAGE"),
            ({"engine": "other"}, "UNSUPPORTED_ENGINE"),
        ):
            async with client_for(server) as c:
                await c.send(type="start", **kw)
                err = await c.recv_json()
                assert err["code"] == code and err["request_id"] is None
                await asyncio.wait_for(c.pump, 5)
                assert await c.call.code() == grpc.StatusCode.OK
        assert server.admission.active == 0
