# Data Model: VibeVoice Engine

No new persistent domain data; the entities extend existing ones.

## VibeVoiceEngine (adapter)
- `name = "vibevoice"`; implements `TTSEngine` (`start`, `capabilities`, `synthesize`, `stop`).
- State: loaded model handle, device (`cpu` | `mps`), model checksum, worker thread, bounded block queue.
- Lifecycle: `unloaded -> loading -> ready -> stopped`; load is lazy and idempotent; `stop` is idempotent.
- Capabilities: languages `["es"]`, voices = verified Spanish presets only, audio `pcm_s16le`/24 kHz/mono
  (confirm in spike), `streaming_mode` per R-04, `execution_provider` = device actually used.

## Voice
- Fields: `name`, `candidate` (shipped preset), `verified` (bool), `manual_signoff` (bool).
- Rule: only voices with `verified = true` for the installed model checksum are exposed. User-supplied
  voices are rejected (spec Q3).

## VerificationResult (per engine)
- File: `verification/vibevoice-verification.json` (same shape as the Kokoro file): model name and sha256,
  recognizer, thresholds, per-voice `mean_wer`, `max_sentence_wer`, `passed`, optional `manual_signoff`.
- Rule: stale checksum => no voices exposed. Zero passing voices => engine refuses with
  `ENGINE_UNAVAILABLE` (FR-007a).

## EngineTransportSupport
- Registry mapping `engine name -> set of supported transports` (`kokoro`, `mock`: websocket+grpc;
  `vibevoice`: websocket).

## MeasurementRecord
- Rows added to `docs/measurements.md` for engine `vibevoice`: TTFA (cold and warm), inter-chunk delay,
  RTF, peak memory, cancel latency, device, model version, trial count, median and p95.
