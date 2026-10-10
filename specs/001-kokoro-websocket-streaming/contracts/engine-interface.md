# Contract: TTS Engine Interface

The transport and session code depend only on this interface (`src/voxstream/engines/base.py`).
No engine-specific type may appear in it.

```text
class TTSEngine(Protocol):
    name: str

    async def start(self) -> None
        # Load model/resources. May be called lazily on first request or at startup.
        # Raises EngineUnavailableError with an actionable message if it cannot load.

    def capabilities(self) -> EngineCapabilities
        # languages, verified voices, audio format, streaming_mode, supports_cancel,
        # execution_provider, memory_notes, model identity (version/checksum).

    def synthesize(self, text: str, voice: str, cancel: CancelToken) -> AsyncIterator[AudioBlock]
        # Yields audio for one text segment, in order, as it becomes available.
        # Must stop at its next safe point once `cancel` is set and must not raise for cancellation.
        # Raises EngineError for failures; OutOfMemoryError maps to OUT_OF_MEMORY.

    async def stop(self) -> None
        # Release resources deterministically; idempotent.
```

## Adapter obligations (Principle VII)

Each adapter documents: initialization behavior (eager/lazy, time, memory), inference behavior
(streaming mode, segment size limits), cancellation granularity, shutdown behavior, supported
languages and voices, runtime requirements, and observed memory.

- **Kokoro adapter**: lazy load; one `kokoro-onnx` session; inference in a worker thread;
  cancellation granularity is one inference call; reports `streaming_mode = segmented`; exposes
  only voices that pass `verification/voice-verification.json` for the installed model checksum;
  reports the provider read from the ONNX session; fails with `ENGINE_UNAVAILABLE` rather than
  silently switching provider or voice.
- **Mock adapter**: deterministic output (tone or silence whose length is a function of the text),
  configurable per-segment delay, injectable failure and cancellation points; used by all unit,
  contract and integration tests that must not load a model.

## Engine selection

`VOXSTREAM_ENGINE` (default `kokoro`) resolves through `engines/registry.py`. Adding an engine
means adding an adapter and a registry entry; transports and the session are unchanged.
