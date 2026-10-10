"""Binary audio frame: 16-byte request UUID, uint32 BE sequence, 1-byte flags, PCM payload."""

from __future__ import annotations

import struct
import uuid
from dataclasses import dataclass

HEADER_SIZE = 21
FLAG_LAST = 0x01
_MAX_SEQ = 0xFFFFFFFF


@dataclass(frozen=True)
class AudioFrame:
    request_id: uuid.UUID
    sequence: int
    last: bool
    payload: bytes


def encode_frame(request_id: uuid.UUID, sequence: int, payload: bytes, last: bool = False) -> bytes:
    if not 0 <= sequence <= _MAX_SEQ:
        raise ValueError("sequence number out of uint32 range")
    return request_id.bytes + struct.pack(">IB", sequence, FLAG_LAST if last else 0) + payload


def decode_frame(data: bytes) -> AudioFrame:
    if len(data) < HEADER_SIZE:
        raise ValueError(f"frame shorter than {HEADER_SIZE} bytes")
    seq, flags = struct.unpack(">IB", data[16:HEADER_SIZE])
    return AudioFrame(uuid.UUID(bytes=data[:16]), seq, bool(flags & FLAG_LAST), data[HEADER_SIZE:])
