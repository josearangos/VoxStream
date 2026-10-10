import json
import logging

from helpers import client_for, running_server
from voxstream.engines.mock import MockEngine
from voxstream.logging import JsonFormatter

SECRET = "Contraseña ultrasecreta zanahoria."


async def test_logs_have_request_id_and_stages_but_no_text():
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
        async with running_server(MockEngine()) as server, client_for(server) as c:
            await c.start()
            await c.text(SECRET)
            await c.end()
            await c.collect()
    finally:
        log.removeHandler(handler)
    joined = "\n".join(records)
    assert "zanahoria" not in joined and "ultrasecreta" not in joined
    parsed = [json.loads(r) for r in records]
    stages = {p.get("stage") for p in parsed}
    assert {"engine_init", "segment_synth", "chunk_sent", "request_end"} <= stages
    assert any(p["request_id"] for p in parsed if p.get("stage") == "segment_synth")
    assert all(p["transport"] == "websocket" for p in parsed if p.get("stage") == "segment_synth")
    assert "transport" in parsed[0]
