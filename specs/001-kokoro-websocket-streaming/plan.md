# Implementation Plan: Kokoro Spanish TTS Streaming over WebSocket

**Branch**: `001-kokoro-websocket-streaming` | **Date**: 2026-10-10 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `/specs/001-kokoro-websocket-streaming/spec.md`

## Summary

A local Python asyncio service that accepts streamed Spanish text over a WebSocket, splits it into
speakable segments as it arrives, synthesizes each segment with Kokoro-ONNX, and streams PCM audio
back as binary frames while the text is still coming in. The transport talks only to a common
`TTSEngine` interface; a deterministic mock engine implements the same interface for tests.
Bounded queues provide backpressure, cancellation and disconnects tear the pipeline down
deterministically, and every error is a structured JSON message. A separate verification command
transcribes audio from each Kokoro Spanish voice with a Spanish speech-recognition model and gates
which voices the service exposes. See [research.md](research.md) for decisions and open risks.

## Technical Context

**Language/Version**: Python 3.12 (kokoro-onnx supports 3.10–3.13; the host default, 3.14, is
not supported, so the project pins 3.12 through `uv`)

**Primary Dependencies**: `websockets` (asyncio server), `pydantic` v2 + `pydantic-settings`,
`kokoro-onnx`, `onnxruntime`, `numpy`. Optional `verify` extra: `faster-whisper`, `jiwer`.
Dev: `pytest`, `pytest-asyncio`, `ruff`, `mypy`.

**Storage**: Files only: model files under `models/` (git-ignored) and the voice verification
result at `verification/voice-verification.json`.

**Testing**: pytest with a deterministic mock engine for unit, contract and integration tests; Kokoro
and recognition-model tests are marked `slow`/`model` and excluded by default.

**Target Platform**: macOS 26 on Apple Silicon (M2 Pro, 16 GB); CPU execution is the guaranteed
baseline, Core ML evaluated separately.

**Project Type**: single Python package exposing a local network service plus a small CLI.

**Performance Goals**: first audio under 1 s after the text piece that completes the first
sentence; real-time factor below 1.0; cancel stops audio within 500 ms (SC-001, SC-002, SC-004).

**Constraints**: bind to 127.0.0.1 by default; one active request service-wide by default;
2,000 characters of text per request; bounded text and audio buffers; no network access during
inference.

**Scale/Scope**: one local client at a time; one engine implementation (Kokoro) plus mock; single
transport (WebSocket). gRPC and VibeVoice are out of scope.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Status | How the plan satisfies it |
|-----------|--------|---------------------------|
| I. Real-time streaming first | Pass | Segment-by-segment synthesis while text arrives; completion, cancel, error messages; bounded queues; per-request timing separates generation from delivery. |
| II. Engine-agnostic | Pass | `TTSEngine` interface; transport imports only the interface; engine chosen by config; Kokoro isolated in `engines/kokoro`. |
| III. Transport parity | Pass (scoped) | Only WebSocket is built here, but the message set in [contracts](contracts/websocket-protocol.md) is transport-neutral so gRPC can mirror it later. |
| IV. Local-first / Apple Silicon | Pass | CPU baseline, no CUDA; the provider actually used is reported; Core ML evaluated as a separate measured task (R-03). |
| V. Memory-constrained | Pass | Lazy model load; one model at a time; bounded buffers; OOM mapped to a structured error. |
| VI. Explicit contracts | Pass | Request ids, sequence numbers, format, completion/error events and engine streaming mode defined in contracts. Streaming mode reported as `segmented`, not true incremental. |
| VII. Engine compatibility | Pass | Kokoro baseline first; each adapter declares init/inference/cancel/shutdown; unsupported config fails with an actionable error. |
| VIII. Reliability | Pass | Validation, limits, admission control (1), idle/request timeouts, deterministic cleanup, `/healthz` and `/readyz`. |
| IX. Quality / testability | Pass | Typed code, layered modules, shared contract tests run against mock and Kokoro, ruff and mypy automated. |
| X. Observability | Pass | Correlation id per request, structured logs by stage, timing in the `completed` message; no text or audio in logs by default. |
| XI. Simplicity | Pass | One process, asyncio, no broker or database. |
| XII. Security / privacy | Pass | Localhost bind default, request limits, pinned versions via `uv.lock`, documented model sources. |
| XIII. Documentation | Pass | README, quickstart, contracts, example client; tested versus experimental stated. |
| XIV. Spanish audio | Pass | Voice allow-list from verification; non-Spanish rejected; Spanish fixtures and examples. |

No violations, so Complexity Tracking is empty. **Post-design re-check (after Phase 1): still
passes.** The one watch item is Principle VII, which requires the Core ML provider to be
validated on its own; it is planned as a research/benchmark task, not assumed.

## Project Structure

### Documentation (this feature)

```text
specs/001-kokoro-websocket-streaming/
├── plan.md
├── research.md
├── data-model.md
├── quickstart.md
├── contracts/
│   ├── websocket-protocol.md
│   └── engine-interface.md
├── checklists/requirements.md
└── tasks.md             # created later by /speckit-tasks
```

### Source Code (repository root)

```text
pyproject.toml
uv.lock
README.md
models/                       # downloaded model files (git-ignored)
verification/
└── voice-verification.json    # output of the Spanish voice check
src/voxstream/
├── config.py                  # settings (env VOXSTREAM_*), limits, defaults
├── errors.py                  # error codes and structured error type
├── logging.py                 # logging setup, request-id context
├── core/
│   ├── session.py             # per-request pipeline: text in, audio out, cancel
│   ├── segmenter.py           # incremental Spanish text segmenter
│   ├── admission.py           # concurrency limit
│   └── metrics.py             # per-request timing record
├── engines/
│   ├── base.py                # TTSEngine interface, capabilities, audio block
│   ├── registry.py            # engine selection from config
│   ├── mock.py                # deterministic test engine
│   └── kokoro/
│       ├── engine.py          # Kokoro-ONNX adapter
│       └── voices.py          # Spanish voice list and verification gate
├── transports/
│   └── websocket/
│       ├── server.py          # connection handling, health/ready HTTP routes
│       ├── messages.py        # JSON message models
│       └── framing.py         # binary audio frame header encode/decode
├── verification/
│   └── spanish.py             # transcribe-and-compare voice check
└── cli.py                     # serve, verify-voices commands
examples/
└── ws_client.py               # streaming-text client that plays/saves audio
tests/
├── unit/                      # segmenter, framing, config, errors, engine adapter, session
├── contract/                  # protocol tests, run against mock and Kokoro
└── integration/               # full WebSocket text-to-audio flows
```

**Structure Decision**: Single package with a src layout. `core` has no knowledge of WebSocket or
Kokoro; `transports` and `engines` depend on `core`/`engines.base` only, which keeps the engine
abstraction free of transport details and lets a gRPC transport be added beside `websocket/`.

## Complexity Tracking

No constitution violations to justify.
