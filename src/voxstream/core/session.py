"""Per-request pipeline: text in -> segments -> engine -> frames out, with cancel and timeouts."""

from __future__ import annotations

import asyncio
import time
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Literal

from voxstream.config import Settings
from voxstream.core.frames import AudioFrame
from voxstream.core.metrics import RequestTiming, SegmentTiming
from voxstream.core.segmenter import Segment, Segmenter
from voxstream.engines.base import (
    CancelToken,
    EngineError,
    EngineUnavailableError,
    OutOfMemoryError,
    TTSEngine,
)
from voxstream.errors import ErrorCode, VoxStreamError
from voxstream.logging import (
    STAGE_CHUNK_SENT,
    STAGE_REQUEST_END,
    STAGE_SEGMENT_SYNTH,
    log_stage,
    logger,
    request_id_var,
)

State = Literal["OPEN", "ENDING", "COMPLETED", "CANCELLED", "FAILED"]
TERMINAL: frozenset[str] = frozenset({"COMPLETED", "CANCELLED", "FAILED"})
SEGMENT_QUEUE_SIZE = 4
BYTES_PER_SAMPLE = 2
SAMPLE_RATE = 24000


def map_exception(exc: BaseException) -> VoxStreamError:
    """Map any exception to a structured error without leaking internal detail."""
    if isinstance(exc, VoxStreamError):
        return exc
    if isinstance(exc, OutOfMemoryError | MemoryError):
        return VoxStreamError(
            ErrorCode.OUT_OF_MEMORY,
            "The engine ran out of memory. Close other applications or use a smaller model.",
        )
    if isinstance(exc, EngineUnavailableError):
        return VoxStreamError(
            ErrorCode.ENGINE_UNAVAILABLE,
            "The speech engine is not available. Check that the model files are installed.",
        )
    if isinstance(exc, EngineError):
        return VoxStreamError(
            ErrorCode.ENGINE_FAILURE,
            "The speech engine failed while synthesizing. Retry with different text.",
        )
    return VoxStreamError(ErrorCode.INTERNAL_ERROR, "An internal error occurred.")


@dataclass
class SessionResult:
    state: State
    audio_frames: int
    audio_ms: float
    chars: int
    timing: RequestTiming
    error: VoxStreamError | None = None


SendAudio = Callable[[AudioFrame], Awaitable[None]]


@dataclass
class _Counters:
    frames_sent: int = 0
    audio_bytes: int = 0
    chars: int = 0
    non_ws_chars: int = 0
    last_activity: float = field(default_factory=time.monotonic)


class Session:
    def __init__(
        self,
        request_id: uuid.UUID,
        engine: TTSEngine,
        voice: str,
        settings: Settings,
        send_audio: SendAudio,
    ) -> None:
        self.request_id = request_id
        self.engine = engine
        self.voice = voice
        self.settings = settings
        self._send_audio = send_audio
        self.state: State = "OPEN"
        self.timing = RequestTiming()
        self.cancel_token = CancelToken()
        self.segmenter = Segmenter(settings.max_pending_chars)
        self.segment_queue: asyncio.Queue[Segment | None] = asyncio.Queue(SEGMENT_QUEUE_SIZE)
        self.audio_queue: asyncio.Queue[bytes | None] = asyncio.Queue(settings.audio_queue_frames)
        self._c = _Counters()
        self._done = asyncio.Event()
        self._result: SessionResult | None = None
        self._tasks: list[asyncio.Task[None]] = []
        self._runner: asyncio.Task[None] | None = None
        self._timeout_error: VoxStreamError | None = None
        self._feeding = False
        self._deadline = time.monotonic() + settings.request_timeout_s
        self._frame_bytes = SAMPLE_RATE * settings.frame_ms // 1000 * BYTES_PER_SAMPLE

    # -- public API ---------------------------------------------------------------------------

    def start(self) -> None:
        self._runner = asyncio.create_task(self._run())

    @property
    def terminal(self) -> bool:
        return self.state in TERMINAL

    @property
    def cancelled(self) -> bool:
        return self.state == "CANCELLED"

    @property
    def chars_received(self) -> int:
        return self._c.chars

    async def feed(self, text: str) -> None:
        if self.state != "OPEN":
            raise VoxStreamError(
                ErrorCode.NO_ACTIVE_REQUEST, "No open request is accepting text on this connection."
            )
        if self._c.chars + len(text) > self.settings.max_text_chars:
            raise VoxStreamError(
                ErrorCode.TEXT_TOO_LONG,
                f"Total text exceeds the limit of {self.settings.max_text_chars} characters.",
            )
        self._c.chars += len(text)
        self._c.last_activity = time.monotonic()
        if not text.strip():
            return
        self._c.non_ws_chars += len(text.strip())
        self.timing.mark_first_text()
        self._feeding = True  # blocked on backpressure is not idleness
        try:
            await self._enqueue(self.segmenter.push(text))
        finally:
            self._feeding = False
            self._c.last_activity = time.monotonic()

    async def end(self) -> None:
        if self.state != "OPEN":
            raise VoxStreamError(
                ErrorCode.NO_ACTIVE_REQUEST, "No open request is accepting text on this connection."
            )
        if self._c.non_ws_chars == 0:
            raise VoxStreamError(ErrorCode.EMPTY_REQUEST, "The request ended without any text.")
        self.state = "ENDING"
        await self._enqueue(self.segmenter.flush())
        await self.segment_queue.put(None)

    def cancel(self) -> None:
        self._finish("CANCELLED")

    def fail(self, error: VoxStreamError) -> None:
        self._finish("FAILED", error)

    async def wait(self) -> SessionResult:
        await self._done.wait()
        assert self._result is not None
        return self._result

    # -- internals ----------------------------------------------------------------------------

    async def _enqueue(self, segments: list[Segment]) -> None:
        for seg in segments:
            self.timing.mark_first_segment()
            await self.segment_queue.put(seg)

    async def _run(self) -> None:
        token = request_id_var.set(str(self.request_id))
        try:
            synth = asyncio.create_task(self._synthesize())
            sender = asyncio.create_task(self._send())
            watch = asyncio.create_task(self._watch())
            self._tasks = [synth, sender, watch]
            try:
                await asyncio.gather(synth, sender)
            except asyncio.CancelledError:
                raise
            except BaseException as exc:
                if not isinstance(exc, VoxStreamError):
                    logger.error("pipeline failure: %s", type(exc).__name__)
                self._finish("FAILED", map_exception(exc))
                return
            if self._timeout_error is not None:
                self._finish("FAILED", self._timeout_error)
            else:
                self._finish("COMPLETED")
        finally:
            request_id_var.reset(token)

    async def _synthesize(self) -> None:
        while True:
            seg = await self.segment_queue.get()
            if seg is None:
                break
            buf = bytearray()
            gen_s = 0.0
            audio_bytes = 0
            stream = self.engine.synthesize(seg.text, self.voice, self.cancel_token).__aiter__()
            while True:
                t0 = time.perf_counter()
                try:
                    block = await stream.__anext__()
                except StopAsyncIteration:
                    gen_s += time.perf_counter() - t0
                    break
                gen_s += time.perf_counter() - t0
                if self.cancel_token.cancelled:
                    return
                if block.sample_rate != SAMPLE_RATE or block.channels != 1:
                    raise EngineError("engine produced an unexpected audio format")
                self.timing.mark_first_audio_generated()
                data = block.samples.tobytes()
                audio_bytes += len(data)
                buf += data
                while len(buf) >= self._frame_bytes:
                    await self.audio_queue.put(bytes(buf[: self._frame_bytes]))
                    del buf[: self._frame_bytes]
            if buf:
                await self.audio_queue.put(bytes(buf))
            audio_ms = audio_bytes / BYTES_PER_SAMPLE / SAMPLE_RATE * 1000
            self.timing.segments.append(SegmentTiming(len(seg.text), gen_s * 1000, audio_ms))
            log_stage(
                STAGE_SEGMENT_SYNTH,
                text_chars=len(seg.text),
                synthesis_ms=round(gen_s * 1000, 1),
                audio_ms=round(audio_ms, 1),
            )
        await self.audio_queue.put(None)

    async def _send(self) -> None:
        rid = self.request_id
        while True:
            payload = await self.audio_queue.get()
            if payload is None:
                if self._c.frames_sent:
                    # Terminator: the last-frame flag rides on an empty frame so that the tail of
                    # every segment can be sent without waiting for the next segment.
                    await self._send_audio(AudioFrame(rid, self._c.frames_sent, True, b""))
                    self._c.frames_sent += 1
                return
            await self._send_audio(AudioFrame(rid, self._c.frames_sent, False, payload))
            self.timing.mark_first_audio_sent()
            self._c.frames_sent += 1
            self._c.audio_bytes += len(payload)
            log_stage(STAGE_CHUNK_SENT, bytes=len(payload), seq=self._c.frames_sent - 1)

    async def _watch(self) -> None:
        idle = self.settings.idle_timeout_s
        while True:
            now = time.monotonic()
            wait = self._deadline - now
            if self.state == "OPEN":
                wait = min(wait, self._c.last_activity + idle - now)
            await asyncio.sleep(max(wait, 0.05 if self._feeding else 0.0))
            now = time.monotonic()
            if now >= self._deadline:
                self._finish(
                    "FAILED",
                    VoxStreamError(
                        ErrorCode.REQUEST_TIMEOUT,
                        "The request exceeded its maximum duration. Retry with less text.",
                    ),
                )
                return
            if self.state == "OPEN" and not self._feeding and now >= self._c.last_activity + idle:
                # Speak the complete segments already queued, then fail.
                self._timeout_error = VoxStreamError(
                    ErrorCode.IDLE_TIMEOUT,
                    "No text or end message arrived within the idle timeout.",
                )
                self.state = "ENDING"
                await self.segment_queue.put(None)
                return

    def _finish(self, state: State, error: VoxStreamError | None = None) -> None:
        if self.state in TERMINAL:
            return
        self.state = state
        self.cancel_token.cancel()
        current = asyncio.current_task()
        for task in [*self._tasks, self._runner]:
            if task is not None and task is not current and not task.done():
                task.cancel()
        for q in (self.segment_queue, self.audio_queue):
            while not q.empty():
                q.get_nowait()
        self.timing.mark_end()
        self._result = SessionResult(
            state=state,
            audio_frames=self._c.frames_sent,
            audio_ms=self._c.audio_bytes / BYTES_PER_SAMPLE / SAMPLE_RATE * 1000,
            chars=self._c.chars,
            timing=self.timing,
            error=error,
        )
        log_stage(STAGE_REQUEST_END, state=state, frames=self._c.frames_sent, chars=self._c.chars)
        self._done.set()
