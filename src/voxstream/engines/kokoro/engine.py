"""Kokoro-ONNX adapter.

Initialization: lazy, loads the ONNX session in a worker thread (about 1 s, ~0.6 GB resident).
Inference: one ``create_stream`` call per text segment; audio is yielded batch by batch
(streaming_mode ``segmented``). Cancellation: checked between batches; the batch already running
in the worker thread finishes and is discarded. Shutdown: ``stop`` drops the session; idempotent.
"""

from __future__ import annotations

import asyncio
import contextlib
import hashlib
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

import numpy as np

from voxstream.config import Settings
from voxstream.engines.base import (
    AudioBlock,
    CancelToken,
    EngineCapabilities,
    EngineError,
    EngineUnavailableError,
    OutOfMemoryError,
)
from voxstream.engines.kokoro.voices import CANDIDATE_VOICES, LANGUAGE, VoiceGate, load_gate
from voxstream.logging import logger

_PROVIDERS = {
    "cpu": ["CPUExecutionProvider"],
    "coreml": ["CoreMLExecutionProvider", "CPUExecutionProvider"],
}
_PROVIDER_NAMES = {"cpu": "CPUExecutionProvider", "coreml": "CoreMLExecutionProvider"}


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


class KokoroEngine:
    name = "kokoro"

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._model_path = Path(settings.models_dir) / settings.model_file
        self._voices_path = Path(settings.models_dir) / settings.voices_file
        self._kokoro: Any = None
        self._provider: str | None = None
        self._sha: tuple[tuple[float, int], str] | None = None
        self._load_lock = asyncio.Lock()

    # -- model identity and voice gate ---------------------------------------------------------

    def model_sha256(self) -> str | None:
        if not self._model_path.exists():
            return None
        st = self._model_path.stat()
        key = (st.st_mtime, st.st_size)
        if self._sha is None or self._sha[0] != key:
            self._sha = (key, _sha256(self._model_path))
        return self._sha[1]

    def gate(self) -> VoiceGate:
        if self.settings.allow_unverified_voices:
            return VoiceGate(
                voices=list(CANDIDATE_VOICES),
                warnings=["Unverified voices are enabled (spike mode); do not use in production."],
            )
        return load_gate(Path(self.settings.verification_file), self.model_sha256())

    def readiness(self) -> tuple[bool, str | None, list[str]]:
        if not self._model_path.exists() or not self._voices_path.exists():
            return False, "Model files not found; run 'voxstream download-models'.", []
        gate = self.gate()
        if not gate.voices:
            return False, gate.reason, gate.warnings
        return True, None, gate.warnings

    # -- TTSEngine -----------------------------------------------------------------------------

    async def start(self) -> None:
        async with self._load_lock:
            if self._kokoro is not None:
                return
            if not self._model_path.exists() or not self._voices_path.exists():
                raise EngineUnavailableError(
                    "Kokoro model files not found; run 'voxstream download-models'."
                )
            try:
                await asyncio.to_thread(self._load)
            except MemoryError as exc:
                raise OutOfMemoryError("out of memory while loading the model") from exc
            except EngineError:
                raise
            except Exception as exc:
                logger.error("kokoro load failed: %s", type(exc).__name__)
                raise EngineUnavailableError("Kokoro failed to load.") from exc

    def _load(self) -> None:
        import onnxruntime as rt
        from kokoro_onnx import Kokoro

        wanted = self.settings.execution_provider.lower()
        if wanted not in _PROVIDERS:
            raise EngineUnavailableError(
                f"Unknown execution provider {wanted!r}; use one of {', '.join(_PROVIDERS)}."
            )
        session = rt.InferenceSession(str(self._model_path), providers=_PROVIDERS[wanted])
        actual = session.get_providers()[0]
        if actual != _PROVIDER_NAMES[wanted]:
            raise EngineUnavailableError(
                f"Execution provider {wanted!r} is not available (got {actual}); "
                "not switching silently."
            )
        self._kokoro = Kokoro.from_session(session, str(self._voices_path))
        self._provider = actual

    def capabilities(self) -> EngineCapabilities:
        return EngineCapabilities(
            name=self.name,
            version=f"kokoro-v1.0 sha256:{(self.model_sha256() or 'missing')[:12]}",
            languages=[LANGUAGE],
            voices=self.gate().voices,
            streaming_mode="segmented",
            supports_cancel="between ONNX batches within a segment",
            execution_provider=self._provider
            or _PROVIDER_NAMES.get(self.settings.execution_provider.lower(), "unknown"),
            memory_notes="about 0.6 GB resident with the full-precision model (CPU)",
        )

    async def synthesize(
        self, text: str, voice: str, cancel: CancelToken
    ) -> AsyncIterator[AudioBlock]:
        if self._kokoro is None:
            await self.start()
        try:
            stream = self._kokoro.create_stream(text, voice=voice, lang=LANGUAGE)
            async with contextlib.aclosing(stream):
                async for samples, rate in stream:
                    if cancel.cancelled:
                        return
                    pcm = (np.clip(samples, -1.0, 1.0) * 32767).astype(np.int16)
                    yield AudioBlock(pcm, rate, 1)
        except MemoryError as exc:
            raise OutOfMemoryError("out of memory while synthesizing") from exc
        except EngineError:
            raise
        except Exception as exc:
            if "alloc" in str(exc).lower():
                raise OutOfMemoryError("out of memory while synthesizing") from exc
            logger.error("kokoro synthesis failed: %s", type(exc).__name__)
            raise EngineError("synthesis failed") from exc

    async def stop(self) -> None:
        self._kokoro = None
        self._provider = None
