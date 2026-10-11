# Research: VibeVoice Spanish Engine (WebSocket)

Sources: [VibeVoice-Realtime-0.5B model card](https://huggingface.co/microsoft/VibeVoice-Realtime-0.5B),
[VibeVoice realtime docs](https://github.com/microsoft/VibeVoice/blob/main/docs/vibevoice-realtime-0.5b.md),
[MLX repackaging](https://huggingface.co/mnmly/VibeVoice-Realtime-0.5B-mlx). Findings below are from
those pages; anything not found there is marked **Unknown** and becomes a spike task, not an assumption.

## R-01 Which VibeVoice model

- **Decision**: Target `VibeVoice-Realtime-0.5B` (MIT license). It is the only variant built for
  streaming text input (about 300 ms to first audio on the vendor's hardware, single speaker).
- **Rationale**: Matches the streaming goal and fits memory (about 1B parameters in BF16, roughly 2 GB
  of weights). Larger long-form VibeVoice variants are not real-time and are out of scope.
- **Alternatives**: Long-form VibeVoice (too large and slow for 16 GB real-time use).

## R-02 Spanish support

- **Finding**: The model card says it is trained on English only; Spanish is one of nine
  "experimental" multilingual voice sets (2 Spanish voices, names Unknown) that must be downloaded
  separately and are "not extensively tested".
- **Decision**: Treat Spanish as unproven. The engine is gated by the existing transcribe-and-compare
  verification (spec FR-007, FR-007a); with zero passing voices it refuses to synthesize.
- **Alternatives**: Assume Spanish works (violates constitution XIV).

## R-03 Runtime on Apple Silicon

- **Finding**: Official install targets NVIDIA containers with flash-attention. The docs say a Mac M4 Pro
  reached real-time but do not name the backend (MPS vs CPU). A community MLX build exists but is only
  documented for Swift (mlx-audio-swift), not Python.
- **Decision**: Spike first (task 1): try the official PyTorch implementation on CPU, then MPS, and
  record which works with 16 GB, using the same provider-honesty rule as Kokoro (never silently fall
  back). The MLX build is a fallback candidate only if a Python loader exists.
- **Risk**: No working Apple Silicon path means the engine cannot be supported (constitution VII);
  the outcome is documented rather than forced.

## R-04 Streaming mode and cancellation

- **Finding**: Python streaming API and stop mechanism are **Unknown** from the docs.
- **Decision**: Spike reads the upstream demo (`demo/vibevoice_realtime_demo.py`, websocket demo) to
  find the audio streamer and its stop hook. The adapter runs generation in a worker thread, feeds
  audio blocks to an asyncio queue (bounded), and sets the upstream stop flag on cancel. Report
  `streaming_mode` honestly: `incremental` only if the model emits audio during generation, else
  `segmented`.

## R-05 Reusing existing design

- **Decision**: Reuse the `TTSEngine` protocol, voice-gate concept, WebSocket protocol, and Spanish
  verification unchanged; generalize only where Kokoro is hard-coded:
  - `verification/spanish.py` and CLI `verify-voices` take the engine name.
  - Voice gate (`engines/kokoro/voices.py`) moves to a shared module parameterized by candidates.
  - Verification results are stored per engine (`verification/<engine>-verification.json`).
- **Rationale**: Constitution II and XI (no redesign, consistent formats).

## R-06 Isolation of dependencies

- **Decision**: New optional extra `vibevoice` in `pyproject.toml` (torch, transformers, vibevoice).
  Imports happen only inside `engines/vibevoice/` and lazily in the registry, so the default install and
  tests do not need torch. A test guards against top-level imports (like the existing lazy-import test).

## R-07 gRPC exclusion

- **Decision**: The registry declares which transports each engine supports. `Settings` validation
  rejects `engine=vibevoice` with gRPC enabled (actionable error). WebSocket-only runs are unaffected.
- **Alternatives**: Let gRPC start and fail per request (obscure, rejected by spec edge case).

## R-08 Sample rate

- **Finding**: Not stated on the pages; the tokenizer is described at 24 kHz.
- **Decision**: Assume 24 kHz mono and confirm in the spike; the adapter resamples only if needed, so
  the stream format stays `pcm_s16le` at the rate reported in the acknowledgement.
