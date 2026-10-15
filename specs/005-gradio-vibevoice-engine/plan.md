# Implementation Plan: VibeVoice Engine in the Gradio Demo

**Branch**: `005-gradio-vibevoice-engine` | **Date**: 2026-10-10 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `/specs/005-gradio-vibevoice-engine/spec.md`

## Summary

The demo (feature 003) already speaks protocol v1, and the service already runs VibeVoice over
WebSocket (feature 004), so audio from VibeVoice should play today. What is missing is awareness of
the engine: the demo never says which engine or voice is speaking, cannot choose a voice, and treats
VibeVoice's slower start as a hang. The plan makes the demo read what the service reports
(`GET /readyz`: engine, ready, reason, voices), show the active engine and the voice actually used
(from the `started` message), send the chosen voice in `start`, show a "preparing speech" status
until the first audio chunk, and map VibeVoice failures to readable messages. No service change, no
engine switching (clarification: read-only selector).

## Technical Context

**Language/Version**: Python 3.12 (`>=3.12,<3.13`)

**Primary Dependencies**: Gradio 6.x and `websockets` (already used by the demo); stdlib `urllib` for the readiness call. No new dependency.

**Storage**: N/A

**Testing**: pytest + pytest-asyncio; existing `running_server(MockEngine)` helper serves `/readyz` and the WebSocket, so no model download

**Target Platform**: macOS (Apple Silicon), desktop browser, service on localhost

**Project Type**: Demo client application (`demo/` package), unchanged structure

**Performance Goals**: Visible state change ≤1 s after Start; Stop silences ≤1 s (SC-004); service-info lookup ≤2 s timeout so the page never blocks

**Constraints**: Localhost only; no service/protocol changes (FR-008); Spanish voices only, as listed by the service (FR-009); existing behavior preserved (FR-010)

**Scale/Scope**: Single local user, one playback

## Constitution Check

| Principle | Status | Note |
|-----------|--------|------|
| I Real-time streaming | Pass | Relay unchanged; first-audio wait is surfaced, not hidden |
| II/VII Engine-agnostic | Pass | Demo reads engine and voices from the service, no per-engine code paths beyond display names and restart hints |
| III Transport parity | Pass | Demo stays WebSocket-only; no benchmark claims |
| IV/V Local, memory | Pass | No model loaded in the demo |
| VI Explicit contracts | Pass | Uses existing `/readyz`, `start.voice/engine`, `started.stream`; see [contracts/demo-service-usage.md](contracts/demo-service-usage.md) |
| VIII Reliability | Pass | Not-ready, unsupported engine/voice and unreachable service all map to messages; Stop works while preparing |
| IX Testability | Pass | New logic is pure (parsing, hints, status) plus tests against mock server |
| X Observability | Pass | Logs add engine and voice names only, never text |
| XI Simplicity | Pass | One new small module, no dependency |
| XII Local privacy | Pass | Readiness call goes to the configured local service only |
| XIII Docs | Pass | README demo section and quickstart updated |
| XIV Spanish audio | Pass | Only voices the service lists (Spanish-verified) are offered |

No violations. Post-design re-check: still passes.

## Project Structure

### Documentation (this feature)

```text
specs/005-gradio-vibevoice-engine/
├── plan.md
├── research.md
├── data-model.md
├── quickstart.md
├── contracts/
│   └── demo-service-usage.md
└── tasks.md             # created by /speckit-tasks
```

### Source Code (repository root)

```text
demo/
├── service_info.py      # NEW: fetch/parse /readyz -> ServiceInfo; restart hint for other engines
├── stream_client.py     # Started gains engine+voice; stream_speech accepts voice and engine
├── playback.py          # Runtime takes voice/engine; "Preparing speech…" until first chunk
├── session.py           # PlaybackSession records engine and voice used
├── errors.py            # Messages for ENGINE_UNAVAILABLE/UNSUPPORTED_ENGINE/UNSUPPORTED_VOICE with next steps
├── app.py               # Engine display, voice dropdown, refresh, "speaking with" line
└── settings.py          # unchanged (readiness URL derived from service_url)

tests/demo/
├── test_service_info.py # NEW
├── test_stream_client.py, test_playback.py, test_errors.py   # extended
README.md                # demo section: engines and voices
```

**Structure Decision**: Extend the existing `demo/` package in place; the only new module is
`service_info.py`. Nothing under `src/voxstream/` changes.

## Complexity Tracking

Not needed.
