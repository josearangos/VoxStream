# Research: Kokoro Spanish TTS Streaming over WebSocket

No `NEEDS CLARIFICATION` markers remain in the Technical Context. Items marked **Unverified** are
documented from public sources and MUST be confirmed on the target machine during implementation
(tracked as tasks), per constitution principles IV, VII and XIV.

## R-01 Python version

- **Decision**: Python 3.12, installed and pinned through `uv`.
- **Rationale**: `kokoro-onnx` documents support for 3.10–3.13. The host default is 3.14.0, which
  is outside that range, so using it would risk dependency build failures.
- **Alternatives**: 3.13 (supported, but newer wheels for `onnxruntime`/`faster-whisper` are more
  likely to lag); 3.14 (unsupported).

## R-02 Kokoro-ONNX engine and model files

- **Decision**: Use the `kokoro-onnx` package with `kokoro-v1.0.onnx` and `voices-v1.0.bin` from
  the project's `model-files-v1.1` GitHub release. Keep them in `models/` with recorded checksums.
  Use the full-precision model first; evaluate the quantized variant (~80 MB versus ~300 MB) as a
  memory/quality trade-off.
- **Rationale**: Documented, offline after download, runs on CPU, reported as near real-time on
  M1-class hardware.
- **Alternatives**: Reference PyTorch Kokoro package (heavier, torch dependency); other Spanish
  TTS models (not requested; kept as fallback if verification fails).
- **Unverified**: real-time factor and time to first audio on the M2 Pro for Spanish text.

## R-03 Execution provider (CPU versus Core ML)

- **Decision**: Default to the CPU provider. Add a configurable provider setting and a measured
  comparison task for the Core ML provider; adopt it only if it is correct, faster, and within
  memory limits. The provider actually in use is read from the ONNX session and reported in
  `/readyz` and the capabilities message.
- **Rationale**: Constitution IV and VII require independent validation; Core ML support for this
  model's dynamic shapes is not established, so it cannot be assumed.
- **Alternatives**: Assume Core ML (rejected: unmeasured); MLX (no confirmed Kokoro-ONNX path).

## R-04 Spanish voices and language code

- **Decision**: Candidate voices are `ef_dora` (female), `em_alex` and `em_santa` (male), language
  code `es`. All three are candidates only; each must pass the verification in R-08 before being
  exposed.
- **Rationale**: Public Kokoro v1.0 voice listings name these three Spanish voices. No quality
  grade was found for Spanish voices, so quality is exactly what verification must establish.
- **Alternatives**: Using other-language voices with Spanish text (rejected by Principle XIV).
- **Unverified**: that `kokoro-onnx` accepts `es` and the phonemizer produces good Spanish
  phonemes on macOS (it relies on espeak-ng).

## R-05 WebSocket server library

- **Decision**: `websockets` (asyncio implementation).
- **Rationale**: Minimal, native asyncio, supports text and binary frames, and lets us answer plain
  HTTP `GET /healthz` and `/readyz` on the same port through its request hook, so no web framework
  is needed (Principle XI).
- **Alternatives**: FastAPI/Starlette + uvicorn (more features than needed, extra layers that
  affect latency measurements); `aiohttp` (comparable, larger surface).

## R-06 Streaming and segmentation strategy

- **Decision**: Incremental segmenter that buffers text pieces and emits a segment at a sentence
  end (`. ! ? … ;` and newline followed by whitespace or end-of-input), ignoring Spanish
  abbreviations (`Sr.`, `Sra.`, `Dr.`, `Dra.`, `etc.`, `pág.`…), decimals and ellipsis inside a
  number. Fallback: if pending text reaches `max_pending_chars` (default 120) without a sentence
  end, cut at the last comma or space. At end-of-text, flush the remainder. Each segment is sent to
  the engine; the engine output for a segment is sliced into fixed-size frames (default 100 ms).
- **Rationale**: Kokoro synthesizes per text chunk and is not token-incremental, so streaming
  quality depends on segmentation. This reports the engine streaming mode honestly as `segmented`
  (Principle VI).
- **Alternatives**: Per-word synthesis (prosody degrades); waiting for the whole text (violates
  the feature purpose).
- **Open trade-off**: a shorter fallback lowers first-audio delay but may cut phrases unnaturally;
  default to be tuned with measurements.

## R-07 Audio format

- **Decision**: PCM signed 16-bit little-endian, 24,000 Hz, mono, converted from the model's float
  output. Binary frame header: 16-byte request UUID, 4-byte big-endian sequence number, 1-byte
  flags (bit 0 = last audio frame of the request), followed by the PCM payload. Control messages
  are JSON text frames. Details in [contracts](contracts/websocket-protocol.md).
- **Rationale**: Uncompressed and trivially playable; 24 kHz is Kokoro's native rate so no
  resampling cost; 16-bit halves bandwidth versus float32.
- **Alternatives**: float32 PCM (double size); Opus/MP3 (encode latency, out of scope).

## R-08 Spanish verification method

- **Decision**: `voxstream verify-voices` synthesizes a fixed set of Spanish reference sentences
  for each candidate voice, transcribes each result with `faster-whisper` (a multilingual Whisper
  model, `small` by default, language forced to `es`, CPU), normalizes both texts (case, accents
  folded for comparison only, punctuation removed) and computes word error rate with `jiwer`.
  A voice passes if its mean WER is at or below a configurable threshold (default 0.15) and no
  sentence exceeds 0.35. Results go to `verification/voice-verification.json` with the model
  checksum, recognizer name, per-sentence WER and a `manual_signoff` field set by
  `verify-voices --signoff <voice>` after the developer listens.
- **Rationale**: Repeatable, offline, matches the clarified decision. The recognizer is an
  optional dependency used only for verification, never at serving time.
- **Gate rule**: the service exposes a voice only when its automated result is a pass for the
  installed model checksum; a missing sign-off is reported as a warning in `/readyz` (the sign-off
  is a one-time human step and must not block automated tests).
- **Alternatives**: Language-ID only (does not prove intelligibility); manual only (not
  repeatable).
- **Unverified**: that the thresholds are appropriate; they are starting points to calibrate.

## R-09 Concurrency, buffering, backpressure

- **Decision**: Per request pipeline of three asyncio tasks joined by bounded queues: receiver
  (reads WebSocket, validates, feeds the segmenter), synthesizer (calls the engine per segment),
  sender (writes frames). Audio queue bound default 8 frames (about 0.8 s); when full the
  synthesizer waits, which stops reading new segments, and the receiver stops reading from the
  socket once pending text hits its bound so TCP backpressure reaches the client. Admission is a
  service-wide semaphore of size 1.
- **Rationale**: Simple, bounded, and each stage can be timed separately.

## R-10 Cancellation

- **Decision**: Cancellation is a shared token plus asyncio task cancellation. The engine
  interface requires `synthesize` to stop at the next safe point after cancellation. Kokoro
  inference runs in a worker thread and cannot be interrupted mid-inference, so cancel latency is
  bounded by the length of one segment's inference; the sender stops immediately and drops audio
  produced after cancel.
- **Rationale**: Honest about the engine limit. SC-004 (500 ms) depends on segment inference time
  and is a measured acceptance test, mitigated by the fallback segment-length cap.
- **Unverified**: inference time per segment on the target machine.

## R-11 Observability

- **Decision**: Standard-library logging with a JSON formatter; a context variable carries the
  request id. Stage events: `engine_init`, `segment_synth` (duration, characters, audio ms),
  `chunk_sent`, `request_end`. Only lengths and counts are logged, never text or audio. A
  per-request timing record (first text piece time, first segment complete, first audio sent,
  generation time per segment, total) is returned in the `completed` message for benchmarking.
- **Alternatives**: OpenTelemetry (more infrastructure than a local service needs now).

## R-12 Configuration

- **Decision**: `pydantic-settings` with `VOXSTREAM_` environment variables and an optional env
  file. Defaults: host `127.0.0.1`, port `8765`, engine `kokoro`, max text 2000 characters, request
  timeout 120 s, idle timeout 15 s, concurrency 1, frame 100 ms, audio queue 8 frames.

## R-13 Tooling

- **Decision**: `uv` for environment and lockfile, `ruff` for lint/format, `mypy` for types,
  `pytest` + `pytest-asyncio` for tests.

## Open risks carried into tasks

1. Spanish quality of Kokoro voices may fail verification; fallback is selecting another
   Spanish-capable model before shipping.
2. Phonemizer (espeak-ng) availability on macOS arm64 must be confirmed.
3. Cancel latency bound by per-segment inference time.
4. Core ML provider may be incorrect or slower; CPU stays the default.

## Spike results

Measured 2026-10-10 on MacBook (Apple M2 Pro, 16 GB, macOS 26.2), Python 3.12.11 under `uv`,
`kokoro-onnx` 0.6.1, `onnxruntime` 1.31.0, `websockets` 17.2.

- **T029 install and phonemizer**: `kokoro-onnx` installs on arm64 under Python 3.12. The phonemizer
  works without Homebrew `espeak-ng`: `espeakng-loader` bundles the library. Language `es` is
  accepted; `ef_dora`, `em_alex` and `em_santa` all synthesize Spanish and appear in
  `Kokoro.get_voices()`.
- **Files** (release `model-files-v1.1`): `kokoro-v1.0.onnx` 325,505,369 bytes; `voices-v1.0.bin`
  28,214,398 bytes; `kokoro-v1.0.int8.onnx` 114,119,327; `kokoro-v1.0.fp16.onnx` 163,527,961.
  Note: the voices file is `voices-v1.0.bin` in both `model-files-v1.0` and `-v1.1`.
- **T034 service run (Kokoro, CPU)**: warm time to first audio (from the text piece that completes
  the first sentence) median 430 ms, p95 448 ms; real-time factor 0.28; peak server RSS 621 MB.
  The first request after start is slower (1.5-1.6 s) because the model loads lazily.
  Details in `docs/measurements.md`.
- **API note**: `kokoro-onnx` 0.6.1 provides `create_stream` (async, batch-wise), used by the adapter.
