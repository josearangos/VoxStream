"""Per-request timing record. Generation and delivery are recorded separately (FR-024)."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any


@dataclass
class SegmentTiming:
    chars: int
    synthesis_ms: float
    audio_ms: float


@dataclass
class RequestTiming:
    t_start: float = field(default_factory=time.monotonic)
    t_first_text: float | None = None
    t_first_segment: float | None = None
    t_first_audio_generated: float | None = None
    t_first_audio_sent: float | None = None
    segments: list[SegmentTiming] = field(default_factory=list)
    t_end: float | None = None

    @staticmethod
    def _ms(a: float | None, b: float | None) -> float | None:
        return None if a is None or b is None else (b - a) * 1000

    def mark_first_text(self) -> None:
        if self.t_first_text is None:
            self.t_first_text = time.monotonic()

    def mark_first_segment(self) -> None:
        if self.t_first_segment is None:
            self.t_first_segment = time.monotonic()

    def mark_first_audio_generated(self) -> None:
        if self.t_first_audio_generated is None:
            self.t_first_audio_generated = time.monotonic()

    def mark_first_audio_sent(self) -> None:
        if self.t_first_audio_sent is None:
            self.t_first_audio_sent = time.monotonic()

    def mark_end(self) -> None:
        self.t_end = time.monotonic()

    @property
    def ttfa_from_first_segment_ms(self) -> float | None:
        return self._ms(self.t_first_segment, self.t_first_audio_sent)

    @property
    def generation_ms(self) -> float:
        return sum(s.synthesis_ms for s in self.segments)

    @property
    def delivery_ms(self) -> float | None:
        return self._ms(self.t_first_audio_sent, self.t_end)

    @property
    def audio_ms(self) -> float:
        return sum(s.audio_ms for s in self.segments)

    @property
    def rtf(self) -> float | None:
        return self.generation_ms / self.audio_ms if self.audio_ms else None

    def to_dict(self) -> dict[str, Any]:
        def r(v: float | None) -> float | None:
            return None if v is None else round(v, 2)

        return {
            "ttfa_from_first_segment_ms": r(self.ttfa_from_first_segment_ms),
            "ttfa_from_first_text_ms": r(self._ms(self.t_first_text, self.t_first_audio_sent)),
            "generation_ms": r(self.generation_ms),
            "delivery_ms": r(self.delivery_ms),
            "total_ms": r(self._ms(self.t_start, self.t_end)),
            "rtf": None if self.rtf is None else round(self.rtf, 3),
            "segments": [
                {"chars": s.chars, "synthesis_ms": r(s.synthesis_ms), "audio_ms": r(s.audio_ms)}
                for s in self.segments
            ],
        }
