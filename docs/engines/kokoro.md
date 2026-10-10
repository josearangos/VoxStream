# Kokoro engine (`engines/kokoro`)

| Item | Value |
|------|-------|
| Package | `kokoro-onnx` 0.6.x with `kokoro-v1.0.onnx` and `voices-v1.0.bin` (release `model-files-v1.1`) |
| Languages | Spanish only (`es`) |
| Candidate voices | `ef_dora`, `em_alex`, `em_santa` |
| Served voices | Only those that pass `voxstream verify-voices` for the installed model checksum |
| Audio | PCM s16le, 24 000 Hz, mono |
| Streaming mode | `segmented`: one text segment per inference; audio yielded batch by batch |
| Runtime | macOS on Apple Silicon, Python 3.12, CPU execution provider by default |
| Memory (observed) | ~0.6 GB resident, full-precision model, CPU (see `docs/measurements.md`) |

## Initialization
Lazy. The ONNX session is created in a worker thread on the first request (about 1 s on an M2 Pro).
`/readyz` and `capabilities` work before the first load because they only read file metadata and the
verification result. A missing model gives `ENGINE_UNAVAILABLE` ("run `voxstream download-models`").
The requested execution provider is never silently replaced: if `VOXSTREAM_EXECUTION_PROVIDER=coreml`
is not what ONNX Runtime actually selected, startup fails with `ENGINE_UNAVAILABLE`.

## Inference and cancellation
Each segment calls `Kokoro.create_stream`, which splits the text into phoneme batches and runs them
in a worker thread. Cancellation is checked between batches: the batch already running finishes and
is discarded, so cancel latency is bounded by one batch (see `docs/measurements.md` for SC-004).

## Shutdown
`stop()` drops the session and is idempotent. The server calls it on shutdown.

## Voice gate
`verification/voice-verification.json` records, per voice, WER against a `faster-whisper small`
transcription of fixed Spanish sentences and the SHA-256 of the model that was checked. A voice is
served only if `passed` is true and the SHA matches the installed `kokoro-v1.0.onnx`. A missing manual
sign-off is a warning in `/readyz`, not a block. `VOXSTREAM_ALLOW_UNVERIFIED_VOICES=true` exists only
for spike work and must not be used in production.
