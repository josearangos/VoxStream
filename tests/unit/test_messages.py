import json

import pytest

from voxstream.errors import ErrorCode, VoxStreamError
from voxstream.transports.websocket import messages as m


@pytest.mark.parametrize(
    "payload,cls",
    [
        ({"type": "start"}, m.StartMsg),
        ({"type": "start", "voice": "ef_dora", "language": "es", "engine": "kokoro"}, m.StartMsg),
        ({"type": "text", "request_id": "x", "text": "hola"}, m.TextMsg),
        ({"type": "end", "request_id": "x"}, m.EndMsg),
        ({"type": "cancel", "request_id": "x"}, m.CancelMsg),
        ({"type": "capabilities"}, m.CapabilitiesMsg),
    ],
)
def test_valid(payload, cls):
    assert isinstance(m.parse_client_message(json.dumps(payload)), cls)


@pytest.mark.parametrize(
    "raw",
    [
        "not json",
        "[]",
        json.dumps({"type": "nope"}),
        json.dumps({}),
        json.dumps({"type": "text", "request_id": "x"}),
        json.dumps({"type": "text", "text": "a"}),
        json.dumps({"type": "end"}),
        json.dumps({"type": "cancel"}),
        json.dumps({"type": "text", "request_id": "x", "text": 5}),
    ],
)
def test_invalid(raw):
    with pytest.raises(VoxStreamError) as ei:
        m.parse_client_message(raw)
    assert ei.value.code == ErrorCode.MALFORMED_MESSAGE


def test_server_messages_shape():
    e = VoxStreamError(ErrorCode.BUSY, "busy")
    d = m.error(e)
    assert d == {
        "type": "error",
        "request_id": None,
        "code": "BUSY",
        "category": "capacity",
        "message": "busy",
        "retryable": True,
    }
    assert m.cancelled("r", 3)["type"] == "cancelled"
    assert m.completed("r", 1, 100.0, 5, {})["type"] == "completed"
