import uuid

import pytest

from voxstream.transports.websocket.framing import HEADER_SIZE, decode_frame, encode_frame


def test_round_trip():
    rid = uuid.uuid4()
    data = encode_frame(rid, 7, b"\x01\x02\x03\x04")
    f = decode_frame(data)
    assert (f.request_id, f.sequence, f.last, f.payload) == (rid, 7, False, b"\x01\x02\x03\x04")
    assert len(data) == HEADER_SIZE + 4


def test_last_flag():
    f = decode_frame(encode_frame(uuid.uuid4(), 0, b"", last=True))
    assert f.last and f.payload == b""


def test_sequence_overflow_rejected():
    with pytest.raises(ValueError):
        encode_frame(uuid.uuid4(), 2**32, b"")
    with pytest.raises(ValueError):
        encode_frame(uuid.uuid4(), -1, b"")


def test_max_sequence_ok():
    assert decode_frame(encode_frame(uuid.uuid4(), 2**32 - 1, b"")).sequence == 2**32 - 1


def test_short_frame_rejected():
    with pytest.raises(ValueError):
        decode_frame(b"\x00" * 20)
