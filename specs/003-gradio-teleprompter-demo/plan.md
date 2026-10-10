# Implementation Plan: Gradio Teleprompter Demo

**Branch**: `003-gradio-teleprompter-demo` | **Date**: 2026-10-10 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `/specs/003-gradio-teleprompter-demo/spec.md`

## Summary

A small browser demo that is a pure client of the existing VoxStream WebSocket service
(feature 001, protocol v1). The user types Spanish text; the demo opens a request, sends the text,
relays the returned PCM frames to the browser as a streaming audio output, and renders the text as
a word-level teleprompter whose highlight follows the audio the browser is actually playing. The
service and its protocol are not modified (FR-012). Word timing is estimated from the characters
per second of audio, then re-scaled once the service reports total audio duration (research R3).

## Technical Context

**Language/Version**: Python 3.12 (same as the service; `>=3.12,<3.13`)

**Primary Dependencies**: Gradio 6.x (UI and streaming audio output), `websockets` (already a dependency)

**Storage**: N/A (text is held only in the session; nothing persisted — FR-011)

**Testing**: pytest + pytest-asyncio; WebSocket client tested against the existing mock engine server; timeline/rendering logic as pure unit tests

**Target Platform**: macOS (Apple Silicon) with a desktop browser; service on localhost

**Project Type**: Demo client application (separate from the service package)

**Performance Goals**: Speech audible ≤2 s after Start for a typical paragraph; highlighted word within 1 s of heard audio; Stop silences ≤1 s (spec SC-002..SC-004)

**Constraints**: Binds to localhost only; no changes to the service; ffmpeg required by Gradio's streaming audio encoder; bounded buffering (relay does not queue unbounded audio)

**Scale/Scope**: Single local user, one active playback; ≤ the service's `max_text_chars` (2,000 by default)

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-checked after Phase 1 design.*

| Principle | Status | Note |
|-----------|--------|------|
| I Real-time streaming | Pass | Audio relayed frame by frame; Stop sends `cancel` |
| II/VII Engine-agnostic | Pass | Demo only speaks the protocol; reads engine info from `started` |
| III Transport parity | Pass | Demo is WebSocket-only, claims no benchmark; not a measurement tool |
| IV/V Local, memory | Pass | No model loaded in the demo; relay buffer bounded (R5) |
| VI Explicit contracts | Pass | Uses protocol v1 as documented; no new messages |
| VIII Reliability | Pass | Every error code mapped to a user message; disconnect and Stop cancel the request |
| IX Testability | Pass | Pure modules + tests against mock engine; no model download in default tests |
| X Observability | Pass | Logs request id and states only, never text or audio |
| XI Simplicity | Pass | One extra dependency (Gradio), optional extra; justified in R1 |
| XII Local privacy | Pass | Gradio bound to 127.0.0.1, sharing disabled; text only goes to local service |
| XIII Docs | Pass | Quickstart + README section |
| XIV Spanish audio | Pass | Default text and examples in Spanish; service rejects non-Spanish |

No violations; Complexity Tracking not needed. Post-design re-check: still passes.

## Project Structure

### Documentation (this feature)

```text
specs/003-gradio-teleprompter-demo/
├── plan.md
├── research.md
├── data-model.md
├── quickstart.md
├── contracts/
│   └── demo-ui.md
└── tasks.md             # created by /speckit-tasks
```

### Source Code (repository root)

```text
demo/
├── __init__.py
├── app.py               # Gradio Blocks UI, event wiring, launch (localhost only)
├── stream_client.py     # Async client of protocol v1: start/text/end/cancel, yields events
├── timeline.py          # Words, per-word time estimates, position lookup, re-scaling
├── teleprompter.py      # Renders HTML for spoken/current/upcoming words
├── audio.py             # PCM frames -> WAV chunk bytes for the streaming audio output
├── errors.py            # Service error code -> plain-language message
├── settings.py          # DEMO_* env settings (service URL, host/port, pacing constants)
├── session.py           # PlaybackSession state and transitions
└── __main__.py          # `python -m demo` entry point

tests/demo/
├── test_timeline.py
├── test_teleprompter.py
├── test_errors.py
├── test_session.py
├── test_audio.py
└── test_stream_client.py   # against the in-repo mock-engine WebSocket server
```

Add an optional dependency group `demo = ["gradio>=6,<7"]` to `pyproject.toml` so the service
install stays unchanged.

**Structure Decision**: A top-level `demo/` package, outside `src/voxstream`, keeps the service
free of UI dependencies and makes the "client only" boundary (FR-012) structural.

## Complexity Tracking

No violations to justify.
