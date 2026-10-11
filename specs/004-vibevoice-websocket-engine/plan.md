# Implementation Plan: Microsoft VibeVoice Spanish Engine (WebSocket)

**Branch**: `004-vibevoice-websocket-engine` | **Date**: 2026-10-10 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `/specs/004-vibevoice-websocket-engine/spec.md`

## Summary

Add a second engine adapter, `vibevoice`, behind the existing `TTSEngine` interface and select it by
configuration. It runs only on the WebSocket transport. Spanish output is unproven for this model, so
the existing transcribe-and-compare verification gates which voices are exposed, and the engine refuses
to synthesize when none pass. Dependencies live in an optional extra and are imported lazily. A first
spike establishes whether an Apple Silicon runtime (CPU or MPS) works, which Python streaming API and
stop hook exist, and the Spanish voice names; the rest of the work follows those findings. See
[research.md](research.md).

## Technical Context

**Language/Version**: Python 3.12 (project pin)

**Primary Dependencies**: existing stack plus optional extra `vibevoice` (PyTorch, transformers, the
upstream `vibevoice` package; exact pins decided by the spike). Verification reuses `faster-whisper`/`jiwer`.

**Storage**: Files only: `models/vibevoice/` (git-ignored) and `verification/vibevoice-verification.json`.

**Testing**: pytest with the mock engine for registry, transport-guard and gate tests; a stub engine
for adapter contract tests; real-model tests marked `model` and excluded by default.

**Target Platform**: macOS on Apple Silicon (M2 Pro, 16 GB), no discrete GPU.

**Project Type**: single Python package (existing service).

**Performance Goals**: first audio chunk within 2 s for a one-sentence request (SC-003); cancel latency
comparable to Kokoro or explained.

**Constraints**: bounded queues; about 2 GB of weights must fit alongside the OS; no network use during
inference; WebSocket only.

**Scale/Scope**: one engine adapter, one registry/settings change, generalized verification and voice
gate, docs and measurements. No protocol changes.

## Constitution Check

| Principle | Status | How the plan satisfies it |
|-----------|--------|---------------------------|
| I. Real-time streaming | Pass | Audio blocks streamed as produced; cancel propagated to the upstream stop hook; bounded queue. |
| II. Engine-agnostic | Pass | New adapter only; transports untouched; dependencies isolated in an extra. |
| III. Transport parity | Justified exception | VibeVoice is WebSocket-only by the spec; Kokoro keeps both. Rationale: scope. Validation: guard test plus documented limitation. |
| IV. Local-first / Apple Silicon | Pass (pending spike) | CPU/MPS only, no CUDA; device actually used is reported; no silent fallback. |
| V. Memory-constrained | Pass (pending spike) | Lazy load, one model at a time, OOM mapped to a structured error, memory measured. |
| VI. Explicit contracts | Pass | Existing protocol; honest `streaming_mode` in capabilities. |
| VII. Engine compatibility | Pass | Compatibility verified in the spike before the engine is called supported; actionable errors. |
| VIII. Reliability | Pass | Existing admission control, timeouts, cleanup; disconnect cancels generation. |
| IX. Testability | Pass | Stub engine tests need no model; real-model tests opt-in. |
| X. Observability | Pass | Same logging; measurements record device, versions, cold/warm. |
| XI. Simplicity | Pass | Reuse of gate, protocol, and verification; one new package directory. |
| XII. Security/privacy | Pass | Localhost default unchanged; model from documented source; no text logged. |
| XIII. Documentation | Pass | README section, engine limitations, quickstart. |
| XIV. Spanish audio | Pass (gated) | Only verified Spanish voices exposed; none verified => refusal; Spanish fixtures. |

Post-design re-check: no new violations; III exception recorded in Complexity Tracking.

## Project Structure

### Documentation (this feature)

```text
specs/004-vibevoice-websocket-engine/
├── plan.md
├── research.md
├── data-model.md
├── quickstart.md
├── contracts/
│   └── engine-vibevoice.md
└── tasks.md             # created by /speckit-tasks
```

### Source Code (repository root)

```text
src/voxstream/
├── config.py                    # + vibevoice_model_dir, vibevoice_device, transport-support check
├── engines/
│   ├── registry.py              # + "vibevoice", per-engine transport support
│   ├── voice_gate.py            # gate moved from engines/kokoro/voices.py (shared)
│   ├── kokoro/                  # imports shared gate
│   └── vibevoice/
│       ├── __init__.py
│       ├── engine.py            # VibeVoiceEngine adapter
│       ├── backend.py           # PyTorch runtime (only module importing torch)
│       └── voices.py            # Spanish candidate presets
├── verification/spanish.py      # engine-parameterized
└── cli.py                       # verify-voices / download-models accept --engine

tests/
├── unit/                        # gate, registry, settings guard, adapter with stub
├── contract/                    # shared engine contract tests, now incl. stub vibevoice
├── integration/                 # lazy-import guard, websocket flow with stub engine
└── integration/test_vibevoice_real.py  # real VibeVoice (marked `model`, excluded by default)

docs/measurements.md             # + VibeVoice rows
README.md                        # + VibeVoice setup and limitations
pyproject.toml                   # + optional extra "vibevoice"
```

**Structure Decision**: Single existing package; the new engine is one subpackage mirroring Kokoro.

## Complexity Tracking

| Violation | Why Needed | Simpler Alternative Rejected Because |
|-----------|------------|-------------------------------------|
| III: engine not on gRPC | Spec limits this feature to WebSocket | Building gRPC support too widens scope; guard error keeps behavior explicit |
