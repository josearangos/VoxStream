import json
import logging

import pytest

from helpers import client_for, running_server
from voxstream.engines.mock import MockEngine
from voxstream.logging import JsonFormatter

SECRET = "Contraseña ultrasecreta zanahoria."


@pytest.mark.parametrize("transport", ["websocket", "grpc"])
async def test_requests_log_their_transport_and_correlation_id(transport):
    records: list[str] = []

    class Capture(logging.Handler):
        def emit(self, record):
            records.append(self.format(record))

    handler = Capture()
    handler.setFormatter(JsonFormatter())
    log = logging.getLogger("voxstream")
    log.addHandler(handler)
    log.setLevel(logging.INFO)
    try:
        async with running_server(MockEngine()) as server:
            server.transport = transport
            async with client_for(server) as c:
                await c.start()
                await c.text(SECRET)
                await c.end()
                frames, _ = await c.collect()
    finally:
        log.removeHandler(handler)
    joined = "\n".join(records)
    assert "zanahoria" not in joined and "ultrasecreta" not in joined
    assert frames[0].payload.hex()[:32] not in joined
    parsed = [json.loads(r) for r in records]
    for stage in ("segment_synth", "chunk_sent", "request_end"):
        staged = [p for p in parsed if p.get("stage") == stage]
        assert staged, stage
        assert all(p["transport"] == transport for p in staged)
        assert all(p["request_id"] for p in staged)
