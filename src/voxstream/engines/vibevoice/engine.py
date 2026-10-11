"""Microsoft VibeVoice-Realtime-0.5B adapter (WebSocket transport only).

Initialization: lazy and idempotent; the model loads in a worker thread on the configured device
(``cpu`` or ``mps``, never switched silently); about 2 GB of weights, several GB resident.
Inference: generation runs in a worker thread and feeds a bounded queue; audio is yielded as the
model produces it (streaming_mode ``incremental``). Cancellation: checked between blocks and passed
to the upstream ``stop_check_fn``. Shutdown: ``stop`` releases the model; idempotent.
"""

from __future__ import annotations

import asyncio
import concurrent.futures
import contextlib
import hashlib
import threading
from collections.abc import AsyncIterator
from pathlib import Path

import numpy as np

from voxstream.config import Settings
from voxstream.engines.base import (
    AudioBlock,
    AudioFormat,
    CancelToken,
    EngineCapabilities,
    EngineError,
    EngineUnavailableError,
    OutOfMemoryError,
)
from voxstream.engines.vibevoice.backend import Backend, FloatChunk, TorchBackend
from voxstream.engines.vibevoice.voices import CANDIDATE_VOICES, LANGUAGE
from voxstream.engines.voice_gate import VoiceGate, load_gate
from voxstream.logging import logger

QUEUE_BLOCKS = 8
_POLL_S = 0.05
_DOWNLOAD_HINT = "run 'voxstream download-models --engine vibevoice'"


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1 << 22), b""):
            h.update(block)
    return h.hexdigest()


def _is_oom(exc: BaseException) -> bool:
    if isinstance(exc, MemoryError):
        return True
    text = str(exc).lower()
    return "out of memory" in text or "alloc" in text


class VibeVoiceEngine:
    name = "vibevoice"

    def __init__(self, settings: Settings, backend: Backend | None = None) -> None:
        self.settings = settings
        self._dir = Path(settings.vibevoice_model_dir)
        self._weights = self._dir / "model" / "model.safetensors"
        self._backend: Backend = backend or TorchBackend(self._dir, settings.vibevoice_device)
        self._injected = backend is not None
        self._loaded = False
        self._sha: tuple[tuple[float, int], str] | None = None
        self._load_lock = asyncio.Lock()

    # -- model identity and voice gate ---------------------------------------------------------

    def model_sha256(self) -> str | None:
        if self._injected:
            return "injected"
        if not self._weights.exists():
            return None
        st = self._weights.stat()
        key = (st.st_mtime, st.st_size)
        if self._sha is None or self._sha[0] != key:
            self._sha = (key, _sha256(self._weights))
        return self._sha[1]

    def gate(self) -> VoiceGate:
        if self.settings.allow_unverified_voices:
            return VoiceGate(
                voices=list(CANDIDATE_VOICES),
                warnings=["Unverified voices are enabled (spike mode); do not use in production."],
            )
        return load_gate(Path(self.settings.engine_verification_file), self.model_sha256())

    def readiness(self) -> tuple[bool, str | None, list[str]]:
        if not self._injected and not self._weights.exists():
            return False, f"VibeVoice model files not found; {_DOWNLOAD_HINT}.", []
        gate = self.gate()
        if not gate.voices:
            return False, gate.reason, gate.warnings
        return True, None, gate.warnings

    # -- TTSEngine -----------------------------------------------------------------------------

    async def start(self) -> None:
        async with self._load_lock:
            if self._loaded:
                return
            if not self._injected and not self._weights.exists():
                raise EngineUnavailableError(f"VibeVoice model files not found; {_DOWNLOAD_HINT}.")
            try:
                await asyncio.to_thread(self._backend.load)
            except EngineError:
                raise
            except Exception as exc:
                if _is_oom(exc):
                    raise OutOfMemoryError("out of memory while loading the model") from exc
                logger.error("vibevoice load failed: %s", type(exc).__name__)
                raise EngineUnavailableError("VibeVoice failed to load.") from exc
            self._loaded = True

    def capabilities(self) -> EngineCapabilities:
        sha = (self.model_sha256() or "missing")[:12]
        return EngineCapabilities(
            name=self.name,
            version=f"VibeVoice-Realtime-0.5B sha256:{sha}",
            languages=[LANGUAGE],
            voices=self.gate().voices,
            audio_format=AudioFormat(sample_rate=self._backend.sample_rate),
            streaming_mode="incremental",
            supports_cancel="between audio chunks via the upstream stop hook",
            execution_provider=self._backend.device,
            memory_notes="about 2 GB of weights, several GB resident; WebSocket only",
        )

    async def synthesize(
        self, text: str, voice: str, cancel: CancelToken
    ) -> AsyncIterator[AudioBlock]:
        if not self._loaded:
            await self.start()
        if voice not in self.gate().voices:
            raise EngineError(f"Voice {voice!r} is not a verified Spanish voice.")
        loop = asyncio.get_running_loop()
        queue: asyncio.Queue[FloatChunk | BaseException | None] = asyncio.Queue(QUEUE_BLOCKS)
        stop = threading.Event()

        def should_stop() -> bool:
            return stop.is_set() or cancel.cancelled

        def put(item: FloatChunk | BaseException | None) -> bool:
            """Block while the queue is full (backpressure); give up once stopped."""
            fut = asyncio.run_coroutine_threadsafe(queue.put(item), loop)
            while True:
                try:
                    fut.result(timeout=_POLL_S)
                    return True
                except concurrent.futures.TimeoutError:
                    if stop.is_set():
                        fut.cancel()
                        return False

        def produce() -> None:
            try:
                for chunk in self._backend.stream(text, voice, should_stop):
                    if should_stop() or not put(chunk):
                        return
            except BaseException as exc:
                put(exc)
            finally:
                put(None)

        worker = asyncio.ensure_future(asyncio.to_thread(produce))
        try:
            while True:
                try:
                    item = await asyncio.wait_for(queue.get(), _POLL_S)
                except TimeoutError:
                    if cancel.cancelled:
                        return
                    continue
                if item is None or cancel.cancelled:
                    return
                if isinstance(item, BaseException):
                    raise item
                pcm = (np.clip(item, -1.0, 1.0) * 32767).astype(np.int16)
                yield AudioBlock(pcm, self._backend.sample_rate, 1)
        except EngineError:
            raise
        except Exception as exc:
            if _is_oom(exc):
                raise OutOfMemoryError("out of memory while synthesizing") from exc
            logger.error("vibevoice synthesis failed: %s", type(exc).__name__)
            raise EngineError("synthesis failed") from exc
        finally:
            stop.set()
            with contextlib.suppress(Exception):
                await worker

    async def stop(self) -> None:
        if not self._loaded:
            return
        self._loaded = False
        await asyncio.to_thread(self._backend.close)
