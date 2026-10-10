# Adding an engine

1. Implement `TTSEngine` from `src/voxstream/engines/base.py`: `start`, `capabilities`,
   `synthesize(text, voice, cancel) -> AsyncIterator[AudioBlock]`, `stop`.
   - Yield int16 mono blocks at 24 000 Hz (or extend the stream descriptor first).
   - Stop at the next safe point when `cancel.cancelled`; do not raise for cancellation.
   - Raise `EngineError`, `EngineUnavailableError` or `OutOfMemoryError`; never leak paths or text.
   - Optional: `readiness() -> (ok, reason, warnings)` to feed `/readyz`.
2. Create `src/voxstream/engines/<name>/` and register the engine in `engines/registry.py`.
3. Document, in `docs/engines/<name>.md`: initialization, inference and streaming mode, cancellation
   granularity, shutdown, languages, voices, runtime requirements and observed memory
   (constitution Principles II and VII).
4. Add the name to the `engine_name` fixture in `tests/contract/conftest.py`
   (mark it `model` if it loads a large model). The same contract suite must pass unchanged.
5. Verify Spanish output with a voice check before exposing any voice (Principle XIV).
