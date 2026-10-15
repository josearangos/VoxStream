---

description: "Task list for VibeVoice Engine in the Gradio Demo"
---

# Tasks: VibeVoice Engine in the Gradio Demo

**Input**: Design documents from `/specs/005-gradio-vibevoice-engine/`

**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/demo-service-usage.md, quickstart.md

**Tests**: Included (constitution principle IX). Default tests use the in-repo mock engine
(`running_server(MockEngine)` serves `/readyz` and the WebSocket) and need no model download.

**Format**: `- [ ] [TaskID] [P?] [Story?] Description with file path` — `[P]` = can run in parallel
(different files, no dependency on an incomplete task).

## Phase 1: Setup

No new dependency or package is needed (plan: stdlib `urllib`). Nothing to do in this phase.

## Phase 2: Foundational (blocks all user stories)

- [X] T001 [P] Create `demo/service_info.py` with frozen dataclass `ServiceInfo(reachable: bool, engine: str | None, ready: bool, reason: str | None, voices: list[str])`; `reason` truncated to 200 chars; `display_name` property (`kokoro`→"Kokoro", `vibevoice`→"VibeVoice", `None`→"Unknown"); `UNKNOWN` constant for fallback mode (`reachable=False`, empty voices)
- [X] T002 In `demo/service_info.py` add `readyz_url(service_url: str) -> str` (`ws://h:p/v1/stream` → `http://h:p/readyz`; `wss`→`https`) and `async fetch_service_info(service_url: str, timeout_s: float = 2.0) -> ServiceInfo` using `urllib.request` in `asyncio.to_thread`; parse HTTP 200 and 503 bodies (`ready`, `engine`, `voices`, `reason`); on any error, 404 or malformed JSON return `UNKNOWN`
- [X] T003 [P] Extend `Started` in `demo/stream_client.py` with `engine: str | None` and `voice: str | None` read from `msg["stream"]`; add optional `voice` and `engine` parameters to `stream_speech`, included in the `start` message only when not `None`
- [X] T004 [P] Add `engine: str | None = None` and `voice: str | None = None` to `PlaybackSession` in `demo/session.py` (state machine unchanged)
- [X] T005 [P] Tests for T001/T002 in `tests/demo/test_service_info.py`: URL derivation (ws/wss), parsing a ready body, parsing a 503 not-ready body with `reason`, `reason` truncation, unreachable port → `UNKNOWN`, 404 and non-JSON → `UNKNOWN`, against `running_server(MockEngine)` where a live server is needed
- [X] T006 [P] Extend `tests/demo/test_stream_client.py`: `Started` carries engine and voice from the mock server; `start` includes `voice`/`engine` when given and omits them when `None`; unknown voice → `ServiceError("UNSUPPORTED_VOICE")`, wrong engine → `ServiceError("UNSUPPORTED_ENGINE")`

**Checkpoint**: service info fetch and the extended client work and are tested.

## Phase 3: User Story 1 - Hear the teleprompter demo with VibeVoice (Priority: P1) 🎯 MVP

**Goal**: The demo plays VibeVoice speech and shows which engine and voice are speaking, taken from the service.

**Independent Test**: Start the service with VibeVoice, play a Spanish paragraph; audio is incremental, the teleprompter follows, and "VibeVoice" is displayed before and during playback (quickstart §2).

- [X] T007 [US1] In `demo/playback.py` give `Runtime` optional `voice: str | None = None` and `engine: str | None = None` fields, pass them to `stream_speech`, and on `Started` set `session.engine` and `session.voice` and log `request=%s engine=%s voice=%s` (names only, never text)
- [X] T008 [US1] In `demo/app.py` call `fetch_service_info(settings.service_url)` on page load (`demo.load`) and show an info line "`<display_name> · ready`" or "`<display_name> · not ready: <reason>`" (or the fallback note "Engine unknown: service info unavailable; using the service default voice")
- [X] T009 [US1] In `demo/app.py` add a read-only `gr.Radio` (`interactive=False`) with choices Kokoro and VibeVoice, active engine selected, and below it a hint for the other engine from `restart_hint(other)`: "`<Other>` is not running. The service runs `<Active>`; restart it with `VOXSTREAM_ENGINE=<other>` and press Refresh." Add `other_engines`/`restart_hint` helpers to `demo/service_info.py`
- [X] T010 [US1] In `demo/app.py` add a "Speaking with `<engine>` · `<voice>`" line, updated from `session.engine`/`session.voice` once `Started` arrives and kept after playback ends; pass the active engine from the loaded `ServiceInfo` into `Runtime` on Start
- [X] T011 [P] [US1] Extend `tests/demo/test_playback.py`: after a run against the mock server the session records the engine and voice reported by `started`; kokoro-style default behavior (no voice/engine passed) is unchanged
- [X] T012 [P] [US1] Add `tests/demo/test_service_info.py` cases for `display_name`, `other_engines` and `restart_hint` text (names the active engine and the exact `VOXSTREAM_ENGINE=` value)

**Checkpoint**: US1 works end to end; this is the MVP.

## Phase 4: User Story 2 - See engines and choose a voice from the demo (Priority: P2)

**Goal**: The presenter can pick among the active engine's Spanish voices; the choice is sent and honored.

**Independent Test**: With the service on VibeVoice, play the same text with two voices and confirm each run uses its voice; Kokoro shown unavailable (quickstart §3).

- [X] T013 [US2] In `demo/app.py` add a `gr.Dropdown` of voices from `ServiceInfo.voices` (first preselected; `interactive=False` with value "Service default" in fallback mode), and pass the selected voice into `Runtime`
- [X] T014 [US2] In `demo/app.py` add a Refresh button that re-runs `fetch_service_info`, repopulates the info line, engine radio, hint and voice dropdown, and stops any active playback first; disable the dropdown and Refresh while a playback is active
- [X] T015 [P] [US2] Extend `tests/demo/test_playback.py`: a chosen voice reaches the service (mock server reports it in `started`) and is recorded in the session; selecting a voice absent from the service yields the mapped `UNSUPPORTED_VOICE` message
- [X] T016 [P] [US2] Add a test in `tests/demo/test_service_info.py` that the voice list offered equals `ServiceInfo.voices` and is empty (dropdown disabled) in fallback mode, via a small pure helper `voice_choices(info) -> tuple[list[str], str | None]` added to `demo/service_info.py`

**Checkpoint**: US1 and US2 both work independently.

## Phase 5: User Story 3 - Understand VibeVoice-specific failures and delays (Priority: P3)

**Goal**: Slow first audio is visible as "Preparing speech…"; engine refusals produce clear messages with a next step.

**Independent Test**: Start the service with VibeVoice unverified or model missing, press Start; a readable message appears and the demo stays usable. Stop during preparing cancels (quickstart §4).

- [X] T017 [US3] In `demo/playback.py` make `Runtime.status()` return "Preparing speech…" while the session is `Playing` and no audio chunk has arrived (`t0 is None`); keep all existing status texts otherwise (no state-machine change)
- [X] T018 [P] [US3] In `demo/errors.py` update messages: `ENGINE_UNAVAILABLE` → "The speech engine is not ready. If it is VibeVoice, check that its model is downloaded and its voices are verified, then press Refresh."; `UNSUPPORTED_ENGINE` → "The service runs a different engine than the page shows. Press Refresh."; `UNSUPPORTED_VOICE` → "That voice is not available on the service. Press Refresh to reload the voice list."
- [X] T019 [US3] In `demo/app.py` after any `ServiceError` outcome of `ENGINE_UNAVAILABLE`, `UNSUPPORTED_ENGINE` or `UNSUPPORTED_VOICE`, re-fetch service info so the info line and voice list are current without a page reload
- [X] T020 [P] [US3] Extend `tests/demo/test_playback.py`: status is "Preparing speech…" after `started` and before the first chunk (use `MockEngine(delay_s=...)`), becomes "Playing" at the first chunk; `stop()` during preparing ends in Stopped
- [X] T021 [P] [US3] Extend `tests/demo/test_errors.py`: the three updated messages, and that an unknown code still never echoes server text

**Checkpoint**: All three stories work.

## Phase 6: Polish & Cross-Cutting

- [X] T022 [P] Update `README.md` demo section: engine and voice display, voice dropdown, Refresh, "comparing engines = restart the service with `VOXSTREAM_ENGINE=...` and press Refresh", VibeVoice first-audio delay note
- [X] T023 [P] Run `uv run ruff check demo tests/demo` and `uv run mypy` and fix findings
- [X] T024 Run `uv run pytest` (default suite, no model) and confirm all existing demo tests still pass unchanged (SC-006)
- [ ] T025 Execute `quickstart.md` §2–§4 manually with the real VibeVoice service and the Kokoro service; record outcomes (SC-001..SC-005) in `quickstart.md` under a "Validation notes" heading

## Dependencies & Execution Order

- Foundational (T001–T006) blocks all stories; T001→T002; T003, T004 are independent of T001/T002.
- US1 (T007–T012) needs Foundational. T008–T010 edit `demo/app.py` sequentially; T007 before T010.
- US2 (T013–T016) needs US1's `app.py` wiring and `ServiceInfo`; T013→T014 (same file).
- US3 (T017–T021) needs only Foundational for `playback.py`/`errors.py` work (T017, T018, T020, T021) and US1's app wiring for T019.
- Polish after all stories.

## Parallel Opportunities

- Foundational: T001, T003, T004 together; then T005, T006.
- US1: T011 and T012 in parallel with each other once T007/T009 land.
- US3: T017 and T018 in parallel (different files); T020 and T021 in parallel.
- Polish: T022 and T023 in parallel.

## Implementation Strategy

1. **MVP**: Foundational + US1 (T001–T012): VibeVoice plays with the engine and voice shown.
2. Add US2 (voice selection, Refresh), validate, then US3 (preparing state, messages).
3. Finish with Polish, including the manual real-engine pass (T025).
