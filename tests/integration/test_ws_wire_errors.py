"""WebSocket wire-level errors (invalid JSON, binary from client); the gRPC equivalents are in
test_grpc_wire_errors.py."""

from contract.test_errors import check
from helpers import client_for, running_server
from voxstream.engines.mock import MockEngine


async def test_malformed():
    async with running_server(MockEngine()) as server, client_for(server) as c:
        await c.ws.send("not json")
        check(await c.recv_json(), "MALFORMED_MESSAGE", "protocol", False, with_id=False)
        await c.send(type="bogus")
        check(await c.recv_json(), "MALFORMED_MESSAGE", "protocol", False)
        await c.ws.send(b"\x00\x01")
        check(await c.recv_json(), "MALFORMED_MESSAGE", "protocol", False)
        assert (await c.start())["type"] == "started"  # connection kept
