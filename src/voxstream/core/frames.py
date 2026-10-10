"""Transport-neutral audio frame handed from ``Session`` to a transport."""

from __future__ import annotations

import uuid
from dataclasses import dataclass


@dataclass(frozen=True)
class AudioFrame:
    """One chunk of PCM (s16le, mono, 24 kHz). ``last`` marks the empty-payload terminator."""

    request_id: uuid.UUID
    sequence: int
    last: bool
    pcm: bytes
