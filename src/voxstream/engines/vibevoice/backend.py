"""PyTorch backend for VibeVoice-Realtime-0.5B (research R-09).

The only module that imports ``torch``, ``transformers`` and ``vibevoice``; every import is inside a
method so the default install and the registry never need them.
"""

from __future__ import annotations

import copy
import threading
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any, Protocol

import numpy as np
import numpy.typing as npt

from voxstream.engines.base import EngineUnavailableError
from voxstream.engines.vibevoice.voices import SAMPLE_RATE

DEVICES = ("cpu", "mps")
DIFFUSION_STEPS = 5
CFG_SCALE = 1.5

FloatChunk = npt.NDArray[np.float32]


class Backend(Protocol):
    """What the adapter needs from a model runtime; tests inject a fake."""

    device: str
    sample_rate: int

    def load(self) -> None: ...

    def stream(
        self, text: str, voice: str, should_stop: Callable[[], bool]
    ) -> Iterator[FloatChunk]: ...

    def close(self) -> None: ...


class TorchBackend:
    def __init__(self, model_dir: Path, device: str) -> None:
        self.model_dir = model_dir
        self.device = device
        self.sample_rate = SAMPLE_RATE
        self._model: Any = None
        self._processor: Any = None
        self._voices: dict[str, Any] = {}

    def load(self) -> None:
        if self.device not in DEVICES:
            raise EngineUnavailableError(
                f"Unknown VibeVoice device {self.device!r}; use one of {', '.join(DEVICES)}."
            )
        try:
            import torch
            from vibevoice.modular.modeling_vibevoice_streaming_inference import (
                VibeVoiceStreamingForConditionalGenerationInference,
            )
            from vibevoice.processor.vibevoice_streaming_processor import (
                VibeVoiceStreamingProcessor,
            )
        except ImportError as exc:
            raise EngineUnavailableError(
                "VibeVoice dependencies are not installed; run 'uv sync --extra vibevoice'."
            ) from exc
        if self.device == "mps" and not torch.backends.mps.is_available():
            raise EngineUnavailableError(
                "Device 'mps' is not available on this machine; "
                "set VOXSTREAM_VIBEVOICE_DEVICE=cpu. Not switching silently."
            )
        path = str(self.model_dir / "model")
        self._processor = VibeVoiceStreamingProcessor.from_pretrained(path)
        model = VibeVoiceStreamingForConditionalGenerationInference.from_pretrained(
            path,
            torch_dtype=torch.float32,
            attn_implementation="sdpa",
            device_map=None if self.device == "mps" else "cpu",
        )
        if self.device == "mps":
            model.to("mps")
        model.eval()
        model.set_ddpm_inference_steps(num_steps=DIFFUSION_STEPS)
        self._model = model

    def _voice(self, voice: str) -> Any:
        if voice not in self._voices:
            import torch
            from transformers.cache_utils import DynamicCache
            from transformers.modeling_outputs import BaseModelOutputWithPast

            file = self.model_dir / "voices" / f"{voice}.pt"
            if not file.exists():
                raise EngineUnavailableError(
                    f"Voice preset {voice!r} not found; run "
                    "'voxstream download-models --engine vibevoice'."
                )
            # weights_only keeps untrusted pickles from running code (needs torch 2.7.x).
            with torch.serialization.safe_globals([BaseModelOutputWithPast, DynamicCache]):
                self._voices[voice] = torch.load(file, map_location=self.device, weights_only=True)
        return self._voices[voice]

    def stream(
        self, text: str, voice: str, should_stop: Callable[[], bool]
    ) -> Iterator[FloatChunk]:
        import torch
        from vibevoice.modular.streamer import AudioStreamer

        prefilled = self._voice(voice)
        inputs = self._processor.process_input_with_cached_prompt(
            text=text.replace("’", "'"),
            cached_prompt=prefilled,
            padding=True,
            return_tensors="pt",
            return_attention_mask=True,
        )
        inputs = {k: v.to(self.device) if torch.is_tensor(v) else v for k, v in inputs.items()}
        streamer = AudioStreamer(batch_size=1, stop_signal=None, timeout=None)
        stop = threading.Event()
        errors: list[BaseException] = []

        def generate() -> None:
            try:
                self._model.generate(
                    **inputs,
                    max_new_tokens=None,
                    cfg_scale=CFG_SCALE,
                    tokenizer=self._processor.tokenizer,
                    generation_config={"do_sample": False},
                    audio_streamer=streamer,
                    stop_check_fn=lambda: stop.is_set() or should_stop(),
                    verbose=False,
                    refresh_negative=True,
                    all_prefilled_outputs=copy.deepcopy(prefilled),
                )
            except BaseException as exc:
                errors.append(exc)
            finally:
                streamer.end()

        thread = threading.Thread(target=generate, daemon=True, name="vibevoice-generate")
        thread.start()
        try:
            for chunk in streamer.get_stream(0):
                if torch.is_tensor(chunk):
                    chunk = chunk.detach().cpu().to(torch.float32).numpy()
                yield np.asarray(chunk, dtype=np.float32).reshape(-1)
        finally:
            stop.set()
            streamer.end()
            thread.join()
        if errors:
            raise errors[0]

    def close(self) -> None:
        self._model = None
        self._processor = None
        self._voices.clear()
        try:
            import torch

            if self.device == "mps":
                torch.mps.empty_cache()
        except ImportError:
            pass
