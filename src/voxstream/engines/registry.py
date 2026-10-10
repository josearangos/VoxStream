"""Engine selection by name."""

from __future__ import annotations

from voxstream.config import Settings
from voxstream.engines.base import TTSEngine
from voxstream.errors import ErrorCode, VoxStreamError

KNOWN_ENGINES = ("kokoro", "mock")


def create_engine(name: str, settings: Settings) -> TTSEngine:
    if name == "mock":
        from voxstream.engines.mock import MockEngine

        return MockEngine()
    if name == "kokoro":
        from voxstream.engines.kokoro.engine import KokoroEngine

        return KokoroEngine(settings)
    raise VoxStreamError(
        ErrorCode.UNSUPPORTED_ENGINE,
        f"Unknown engine {name!r}. Available engines: {', '.join(KNOWN_ENGINES)}.",
    )
