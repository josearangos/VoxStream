"""Engine interface (see contracts/engine-interface.md). No engine-specific types here."""

from __future__ import annotations

import threading
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import Literal, Protocol

import numpy as np
import numpy.typing as npt

StreamingMode = Literal["incremental", "segmented", "complete_then_chunked"]


class EngineError(Exception):
    """Synthesis failed."""


class EngineUnavailableError(EngineError):
    """Model missing or failed to load; message must be actionable."""


class OutOfMemoryError(EngineError):
    """Memory exhaustion while synthesizing."""


class CancelToken:
    """Thread-safe cancellation flag shared between session and engine."""

    def __init__(self) -> None:
        self._event = threading.Event()

    def cancel(self) -> None:
        self._event.set()

    @property
    def cancelled(self) -> bool:
        return self._event.is_set()


@dataclass(frozen=True)
class AudioBlock:
    samples: npt.NDArray[np.int16]
    sample_rate: int = 24000
    channels: int = 1


@dataclass(frozen=True)
class AudioFormat:
    encoding: str = "pcm_s16le"
    sample_rate: int = 24000
    channels: int = 1


@dataclass(frozen=True)
class EngineCapabilities:
    name: str
    version: str
    languages: list[str]
    voices: list[str]
    audio_format: AudioFormat = field(default_factory=AudioFormat)
    streaming_mode: StreamingMode = "segmented"
    supports_cancel: str = "per-segment"
    execution_provider: str = "cpu"
    memory_notes: str = ""


class TTSEngine(Protocol):
    name: str

    async def start(self) -> None: ...

    def capabilities(self) -> EngineCapabilities: ...

    def synthesize(
        self, text: str, voice: str, cancel: CancelToken
    ) -> AsyncIterator[AudioBlock]: ...

    async def stop(self) -> None: ...
