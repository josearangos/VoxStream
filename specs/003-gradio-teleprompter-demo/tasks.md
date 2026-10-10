---

description: "Task list for the Gradio Teleprompter Demo"
---

# Tasks: Gradio Teleprompter Demo

**Input**: Design documents from `/specs/003-gradio-teleprompter-demo/`

**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/demo-ui.md, quickstart.md

**Tests**: Included (constitution principle IX). Default tests use the in-repo mock engine and
need no model download.

**Format**: `- [ ] [TaskID] [P?] [Story?] Description with file path` — `[P]` = can run in parallel
(different files, no dependency on an incomplete task).

## Phase 1: Setup

- [X] T001 Add optional dependency group `demo = ["gradio>=6,<7"]` to `pyproject.toml` (keep service dependencies unchanged) and confirm `uv sync --extra demo` resolves
- [X] T002 [P] Create package skeletons `demo/__init__.py` and `tests/demo/__init__.py`
- [X] T003 [P] Add `ruff`/`mypy` coverage for `demo/` in `pyproject.toml` (extend `[tool.ruff] src`, `[tool.mypy] files`; add `gradio.*` to the mypy `ignore_missing_imports` override)

## Phase 2: Foundational (blocks all user stories)

- [X] T004 Implement `demo/settings.py`: pydantic-settings class with env prefix `DEMO_` and fields `service_url="ws://127.0.0.1:8765/v1/stream"`, `host="127.0.0.1"`, `port=7860`, `playback_lead_ms=0`, `max_text_chars=2000`, `speech_rate_chars_per_s` (default 14.0, tuned in T031), `pause_weight_comma=3`, `pause_weight_sentence=6`, `pause_weight_linebreak=8`; reject any non-loopback `host` (constitution XII)
- [X] T005 [P] Implement `demo/errors.py`: map every protocol v1 error code (`MALFORMED_MESSAGE`, `NO_ACTIVE_REQUEST`, `REQUEST_MISMATCH`, `BUSY`, `UNSUPPORTED_LANGUAGE`, `UNSUPPORTED_VOICE`, `UNSUPPORTED_ENGINE`, `TEXT_TOO_LONG`, `EMPTY_REQUEST`, `IDLE_TIMEOUT`, `REQUEST_TIMEOUT`, `ENGINE_FAILURE`, `ENGINE_UNAVAILABLE`, `OUT_OF_MEMORY`, `INTERNAL_ERROR`) plus connection failure, empty input and over-length to the plain-language messages in `specs/003-gradio-teleprompter-demo/contracts/demo-ui.md`; unknown codes get a generic message that never echoes server text
- [X] T006 [P] Implement `demo/audio.py`: `pcm_to_wav_chunk(payload: bytes, sample_rate: int, channels: int) -> bytes` wrapping `pcm_s16le` bytes in a WAV header using the stdlib `wave` module, plus `payload_ms(...)` helper
- [X] T007 [P] Implement the session state model in `demo/session.py` per `data-model.md`: `PlaybackSession` dataclass with `state` ∈ {`ready`,`connecting`,`playing`,`finished`,`stopped`,`error`}, `text`, `request_id`, `audio_ms_received`, `total_audio_ms`, `error`, and a transition method that rejects invalid transitions
- [X] T008 [P] Unit tests in `tests/demo/test_errors.py` (every code above maps to a non-empty message, unknown code is generic, no raw server text echoed) and `tests/demo/test_audio.py` (WAV header fields, round-trip frame count, mono 24 kHz) and `tests/demo/test_session.py` (valid and invalid transitions)

**Checkpoint**: foundation ready.

## Phase 3: User Story 1 — Type text and hear it spoken in real time (P1) 🎯 MVP

**Goal**: Text in, speech out in the browser, starting before synthesis finishes.

**Independent Test**: With the service running, enter a Spanish paragraph, press Start; speech
begins within ~2 s and plays to the end; status shows Finished. Empty input shows a message.

- [X] T009 [US1] Implement `demo/stream_client.py`: async generator `stream_speech(url, text)` that connects, sends `{"type":"start"}`, validates `started.stream` (`encoding == "pcm_s16le"`, else raise), sends one `text` message then `end`, and yields typed events — `Started(request_id, sample_rate, channels)`, `AudioChunk(payload, ms)` (strip the 21-byte header, skip empty final payload), `Completed(audio_ms)`, `ServiceError(code)`; connection failures raise a `ServiceUnreachable` error; keep no list of audio (bounded, research R5)
- [X] T010 [P] [US1] Integration test `tests/demo/test_stream_client.py` starting the real WebSocket server with the mock engine (reuse `tests/helpers.py` and `tests/conftest.py` fixtures; add a small mock-engine server fixture in `tests/demo/conftest.py` if they do not fit): event order is `Started`, ≥1 `AudioChunk` before `Completed`; total chunk ms matches `Completed.audio_ms` within one frame; unreachable URL raises `ServiceUnreachable`
- [X] T011 [US1] Implement `demo/app.py` with a Gradio `Blocks` layout from the UI contract: multi-line textbox pre-filled with a Spanish sample paragraph, Start button, status line, streaming `gr.Audio` (`streaming=True`, `autoplay=True`, no upload/record sources, WAV format); Start handler is a generator that validates non-empty text (FR-007), consumes `stream_speech`, yields `pcm_to_wav_chunk(...)` bytes to the audio output, and updates the status line (Ready → Connecting → Playing → Finished)
- [X] T012 [US1] Launch in `demo/app.py` `main()` / `demo/__main__.py`: `demo.queue().launch(server_name=settings.host, server_port=settings.port, share=False)`; log request id and state transitions only, never text or audio (constitution X)
- [ ] T013 [US1] Manual validation: run quickstart scenario 1, record time-to-first-audio in `specs/003-gradio-teleprompter-demo/quickstart.md` notes; if the audio is choppy or silent, check ffmpeg is installed and fix chunk format in `demo/audio.py`

**Checkpoint**: US1 is a working MVP (audio only).

## Phase 4: User Story 2 — Follow the text like a teleprompter (P1)

**Goal**: Word-level highlight in step with what is heard, auto-scrolling.

**Independent Test**: Play a ~1-minute text; the highlighted word stays within ~1 s of the audio,
the view scrolls on its own, and all words are spoken at the end.

- [X] T014 [P] [US2] Implement `demo/timeline.py` per `data-model.md`: `build_timeline(text, chars_per_s)` splitting into words with `index`, `text`, `char_start`, `char_end`, `weight` (= character count plus a pause weight for trailing comma, sentence end and line break), `start_s`, `end_s`; `rescale(total_audio_s)` multiplies all times by one factor so the last word ends at the audio end; `word_at(seconds)` clamps to first/last word; handles line breaks, numbers and punctuation-only input without error; also provide `reanchor(now_s, word_index)`, which shifts the times of all later words so the word at `word_index` starts at `now_s`; default pause weights, all configurable via settings: comma = 3 characters, sentence end = 6, line break = 8
- [X] T015 [P] [US2] Unit tests `tests/demo/test_timeline.py`: monotonic times, rescale ends exactly at total, `word_at` boundaries and clamping, punctuation-only and multi-line text, Spanish accents/ñ/¿¡ preserved, and `reanchor` shifts later words only
- [X] T016 [P] [US2] Implement `demo/teleprompter.py`: `render(text, words, current_index, finished)` returning escaped HTML (HTML-escape all user text) with CSS classes `spoken`, `current`, `upcoming`, preserving original whitespace and line breaks, and an `id` on the current word for auto-scroll; when `finished` is true all words are `spoken`
- [X] T017 [P] [US2] Unit tests `tests/demo/test_teleprompter.py`: classes per index, HTML escaping of `<script>` and `&`, whitespace preserved, finished state
- [X] T018 [US2] Spike (research R2): determine whether `gr.Audio.playback_position` updates during streamed output; if yes wire it as the position signal, otherwise use elapsed wall-clock since the first yielded chunk plus `settings.playback_lead_ms`; record the outcome in `specs/003-gradio-teleprompter-demo/research.md` under R2; if no usable signal exists, decide between the wall-clock fallback and relaxing SC-003 (R3) and record the decision
- [X] T019 [US2] Add the teleprompter panel (`gr.HTML`) to `demo/app.py`: build the timeline on Start, update the panel from the chosen position signal (via `word_at`) while playing, call `reanchor(...)` whenever the position signal updates and `rescale(total_audio_ms/1000)` on `Completed`, mark everything spoken at the end; auto-scroll the current word into view (small `js_on_load`/CSS scroll-into-view on the `current` element)
- [ ] T020 [US2] Manual validation: quickstart scenario 2 with a ~1-minute text; measure drift between heard and highlighted word; if beyond ~1 s adjust `DEMO_PLAYBACK_LEAD_MS` / `speech_rate_chars_per_s` defaults in `demo/settings.py` (this is T031's input) and note results in `quickstart.md`

**Checkpoint**: US1 + US2 deliver the full requested demo.

## Phase 5: User Story 3 — Stop and recover from problems (P2)

**Goal**: Stop works within ~1 s; every failure yields a clear message and a ready state.

**Independent Test**: Press Stop mid-playback → silence ≤1 s, page ready. Stop the service → Start shows an unreachable message with no stuck state.

- [X] T021 [US3] Add `cancel` support to `demo/stream_client.py`: on generator close/cancellation (Stop, page disconnect) send `{"type":"cancel","request_id": ...}` if a request is active, then close the socket; never leave the connection open
- [X] T022 [P] [US3] Tests in `tests/demo/test_stream_client.py`: cancelling after the first chunk results in the server freeing its slot (a following `start` is not `BUSY`); a `BUSY` rejection surfaces `ServiceError("BUSY")`; a `TEXT_TOO_LONG` error surfaces correctly (use a low `max_text_chars` server fixture)
- [X] T023 [US3] Add the Stop button to `demo/app.py` (enabled only while active, wired with Gradio `cancels=[start_event]`), set status to Stopped, stop the teleprompter, and make Start while active stop the active session first so streams never overlap
- [X] T024 [US3] Wire error handling in `demo/app.py`: catch `ServiceUnreachable`, `ServiceError`, dropped connection and over-length pre-check (`len(text) > settings.max_text_chars`, show the limit, send nothing); show `demo/errors.py` messages in the status line, keep already-spoken words marked (edge case), and always return Start to enabled
- [X] T025 [US3] Add the autoplay-blocked hint (contract message table) shown beneath the audio player in `demo/app.py`
- [ ] T026 [US3] Manual validation: quickstart scenarios 3–7 (empty, Stop, service down, busy via `examples/ws_client.py`, too long); record any gaps in `quickstart.md`; check SC-004 over about 10 Stop attempts

## Phase 6: Polish & Cross-Cutting

- [X] T027 [P] Add a "Demo" section to `README.md`: prerequisites (ffmpeg, `uv sync --extra demo`), run command `uv run --extra demo python -m demo.app`, settings table, troubleshooting (no audio, service unreachable, browser autoplay), and the note that teleprompter position is estimated
- [X] T028 [P] Run `uv run ruff check demo tests/demo`, `uv run ruff format --check demo tests/demo` and `uv run mypy` and fix findings
- [X] T029 Run the full suite `uv run --extra demo pytest` to confirm service tests are unaffected and demo tests pass
- [X] T030 Verify the service is unchanged: `git diff --stat -- src/voxstream` shows no changes (FR-012)
- [ ] T031 Finalize defaults in `demo/settings.py` from T020 measurements and confirm SC-001..SC-005 using the `quickstart.md` scenarios (SC-001 by timing a fresh run, SC-004 over about 10 Stop attempts); update status notes in `quickstart.md`

## Dependencies & Execution Order

- Phase 1 → Phase 2 → user stories → Polish.
- **US1** depends only on Phase 2. **US2** depends on US1's `demo/app.py` and stream client (T019 builds on T011) but T014–T017 are independent and can start right after Phase 2. **US3** depends on US1 (T021 extends T009; T023–T025 extend `demo/app.py`).
- Within `demo/app.py` tasks (T011, T012, T019, T023, T024, T025) run sequentially — same file.
- T031 needs T020.

## Parallel Opportunities

- Phase 1: T002, T003 together.
- Phase 2: T005, T006, T007, T008 together after T004.
- US2: T014, T015, T016, T017 together, even while US1 is being finished.
- US1 T010 in parallel with T011 once T009 exists.
- Polish: T027, T028 together.

## Implementation Strategy

1. **MVP**: Phases 1–3 (US1) — audible streaming from a text box. Demo-able immediately.
2. Add US2 (teleprompter) — completes the requested demo; do the T018 spike early because it decides the position signal.
3. Add US3 (Stop and error handling) for robustness.
4. Polish, docs, and tune timing constants from real measurements.
