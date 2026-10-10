"""Transport-neutral service: admission, engine lifecycle, readiness and request opening.

Every transport calls :meth:`VoxStreamService.open_session`, so validation, error codes and the
service-wide concurrency limit are identical by construction.
"""

from __future__ import annotations

import asyncio
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from voxstream.config import Settings
from voxstream.core.admission import AdmissionController
from voxstream.core.session import SendAudio, Session, map_exception
from voxstream.engines.base import EngineCapabilities, TTSEngine
from voxstream.errors import ErrorCode, VoxStreamError
from voxstream.logging import STAGE_ENGINE_INIT, log_stage


@dataclass(frozen=True)
class StreamInfo:
    """What a transport tells the client in its ``started`` event."""

    frame_ms: int
    voice: str
    engine: str
    language: str
    streaming_mode: str
    execution_provider: str
    encoding: str = "pcm_s16le"
    sample_rate: int = 24000
    channels: int = 1


@dataclass
class OpenedSession:
    session: Session
    info: StreamInfo
    release: Callable[[], None]


class VoxStreamService:
    def __init__(self, settings: Settings, engine: TTSEngine) -> None:
        self.settings = settings
        self.engine = engine
        self.admission = AdmissionController(settings.max_concurrent_requests)
        self._engine_lock = asyncio.Lock()
        self._engine_started = False

    def readiness(self) -> dict[str, Any]:
        caps = self.engine.capabilities()
        ok, reason, warnings = True, None, []
        probe = getattr(self.engine, "readiness", None)
        if probe is not None:
            ok, reason, warnings = probe()
        if ok and not caps.voices:
            ok, reason = False, "No verified Spanish voice is available."
        body: dict[str, Any] = {
            "ready": ok,
            "engine": caps.name,
            "execution_provider": caps.execution_provider,
            "voices": caps.voices,
        }
        if reason:
            body["reason"] = reason
        if warnings:
            body["warnings"] = warnings
        return body

    def capabilities(self) -> EngineCapabilities:
        return self.engine.capabilities()

    async def ensure_engine(self) -> None:
        async with self._engine_lock:
            if self._engine_started:
                return
            try:
                await self.engine.start()
            except Exception as exc:
                raise map_exception(exc) from None
            self._engine_started = True
            log_stage(STAGE_ENGINE_INIT, engine=self.engine.name)

    async def open_session(
        self,
        engine: str | None,
        voice: str | None,
        language: str | None,
        send_audio: SendAudio,
    ) -> OpenedSession:
        if engine is not None and engine != self.settings.engine:
            raise VoxStreamError(
                ErrorCode.UNSUPPORTED_ENGINE,
                f"Engine {engine!r} is not available; this service runs {self.settings.engine!r}.",
            )
        if language is not None and language != "es":
            raise VoxStreamError(
                ErrorCode.UNSUPPORTED_LANGUAGE, "Only Spanish ('es') is supported."
            )
        ready = self.readiness()
        if not ready["ready"]:
            raise VoxStreamError(
                ErrorCode.ENGINE_UNAVAILABLE,
                ready.get("reason") or "The speech engine is not ready.",
            )
        caps = self.engine.capabilities()
        if voice is not None and voice not in caps.voices:
            raise VoxStreamError(
                ErrorCode.UNSUPPORTED_VOICE,
                f"Voice {voice!r} is not available. Available voices: {', '.join(caps.voices)}.",
            )
        chosen = voice or (
            self.settings.default_voice
            if self.settings.default_voice in caps.voices
            else caps.voices[0]
        )
        self.admission.acquire()  # raises BUSY when the service limit is reached
        released = False

        def release() -> None:
            nonlocal released
            if not released:
                released = True
                self.admission.release()

        try:
            await self.ensure_engine()
        except BaseException:
            release()
            raise
        caps = self.engine.capabilities()
        session = Session(uuid.uuid4(), self.engine, chosen, self.settings, send_audio)
        info = StreamInfo(
            frame_ms=self.settings.frame_ms,
            voice=chosen,
            engine=caps.name,
            language="es",
            streaming_mode=caps.streaming_mode,
            execution_provider=caps.execution_provider,
        )
        return OpenedSession(session, info, release)
