---

description: "Task list for Kokoro Spanish TTS Streaming over WebSocket"
---

# Tasks: Kokoro Spanish TTS Streaming over WebSocket

**Input**: Design documents from `/specs/001-kokoro-websocket-streaming/`

**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/ (all present)

**Tests**: Included. Constitution Principle IX requires unit, contract and integration tests, with
a mock engine so tests never need a large model. Tests that load Kokoro or the recognition model
carry the pytest marker `model` and are excluded from the default run.

**Organization**: Tasks are grouped by user story. Paths are relative to the repository root
(`/Users/josearangos/Documents/Study/VoxStream`).

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependency on an incomplete task)
- **[Story]**: US1–US5 map to the user stories in spec.md

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Project initialization and tooling

- [X] T001 Create `pyproject.toml` (src layout, package `voxstream`, console script `voxstream = voxstream.cli:main`) pinned to Python 3.12 via `.python-version`; dependencies `websockets`, `pydantic>=2`, `pydantic-settings`, `kokoro-onnx`, `onnxruntime`, `numpy`; extra `verify` = `faster-whisper`, `jiwer`; dev group `pytest`, `pytest-asyncio`, `ruff`, `mypy`; pytest markers `model` and `slow`, default `-m "not model"`; then run `uv lock` to create `uv.lock`
- [X] T002 [P] Create the package skeleton with empty `__init__.py` files for `src/voxstream/`, `src/voxstream/core/`, `src/voxstream/engines/`, `src/voxstream/engines/kokoro/`, `src/voxstream/transports/websocket/`, `src/voxstream/verification/`, and test directories `tests/unit/`, `tests/contract/`, `tests/integration/`, plus `examples/` and `verification/`
- [X] T003 [P] Configure `ruff` (lint + format) and `mypy --strict` for `src/` in `pyproject.toml`; add `.gitignore` entries `models/`, `.venv/`, `__pycache__/`, `.pytest_cache/`, `*.wav` (keep `verification/voice-verification.json` tracked)
- [X] T004 [P] Create `README.md` skeleton with headings for installation, supported macOS and Python versions (macOS on Apple Silicon, Python 3.12), configuration, running, troubleshooting, tested versus experimental (filled in Phase 9)

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Interfaces, config, errors, framing and the mock engine that every story uses

**⚠️ CRITICAL**: No user story work can begin until this phase is complete

- [X] T005 [P] Implement settings in `src/voxstream/config.py` using `pydantic-settings` with prefix `VOXSTREAM_`; defaults: host `127.0.0.1`, port `8765`, engine `kokoro`, `max_text_chars` 2000, `request_timeout_s` 120, `idle_timeout_s` 15, `max_concurrent_requests` 1, `frame_ms` 100, `audio_queue_frames` 8, `max_pending_chars` 120, `execution_provider` `cpu`, `models_dir` `models`, `verification_file` `verification/voice-verification.json`, `default_voice` unset (first verified voice)
- [X] T006 [P] Implement `src/voxstream/errors.py`: `ErrorCode` enum with exactly `MALFORMED_MESSAGE`, `NO_ACTIVE_REQUEST`, `REQUEST_MISMATCH`, `BUSY`, `UNSUPPORTED_LANGUAGE`, `UNSUPPORTED_VOICE`, `UNSUPPORTED_ENGINE`, `TEXT_TOO_LONG`, `EMPTY_REQUEST`, `IDLE_TIMEOUT`, `REQUEST_TIMEOUT`, `ENGINE_FAILURE`, `ENGINE_UNAVAILABLE`, `OUT_OF_MEMORY`, `INTERNAL_ERROR`; category enum `validation`, `capacity`, `engine`, `timeout`, `protocol`, `internal`; `VoxStreamError` carrying code, category, actionable message, `retryable`, optional `request_id`; messages must never contain stack traces, file paths or input text
- [X] T007 [P] Implement `src/voxstream/logging.py`: JSON log formatter, a `contextvars` request-id correlation field, stage names `engine_init`, `segment_synth`, `chunk_sent`, `request_end`; helper that logs only lengths and counts, never text or audio
- [X] T008 [P] Implement the engine interface in `src/voxstream/engines/base.py` per `contracts/engine-interface.md`: `TTSEngine` protocol (`start`, `capabilities`, `synthesize(text, voice, cancel) -> AsyncIterator[AudioBlock]`, `stop`), `EngineCapabilities` (name, version, languages, voices, audio_format, streaming_mode in `incremental|segmented|complete_then_chunked`, supports_cancel, execution_provider, memory_notes), `AudioBlock` (int16 samples, sample_rate, channels), `CancelToken`, `EngineError`, `EngineUnavailableError`, `OutOfMemoryError`
- [X] T009 [P] Implement `src/voxstream/core/metrics.py`: `RequestTiming` with fields `t_start`, `t_first_text`, `t_first_segment`, `t_first_audio_generated`, `t_first_audio_sent`, per-segment `{chars, synthesis_ms, audio_ms}`, `t_end`, and derived `ttfa_from_first_segment_ms`, `generation_ms`, `delivery_ms`, `rtf`; generation and delivery times recorded separately
- [X] T010 [P] Implement `src/voxstream/core/admission.py`: service-wide limiter sized by `max_concurrent_requests` (default 1) with non-blocking acquire that raises `VoxStreamError(BUSY, category capacity)` and a guaranteed release path
- [X] T011 [P] Implement `src/voxstream/transports/websocket/framing.py`: encode/decode the binary audio frame per `contracts/websocket-protocol.md` (16-byte request UUID, 4-byte big-endian uint32 sequence number, 1-byte flags with bit 0 = last frame, then PCM s16le payload); decode rejects frames shorter than 21 bytes
- [X] T012 [P] Implement `src/voxstream/transports/websocket/messages.py`: pydantic models for client messages `start`, `text`, `end`, `cancel`, `capabilities` and server messages `started` (with Stream Descriptor: encoding `pcm_s16le`, sample_rate 24000, channels 1, frame_ms, voice, engine, language, streaming_mode, execution_provider), `capabilities`, `completed`, `cancelled`, `error`; unknown `type` or missing field raises `MALFORMED_MESSAGE`
- [X] T013 [P] Implement the deterministic mock engine in `src/voxstream/engines/mock.py`: output length is a function of text length, configurable per-segment delay, injectable failure at segment N, honors `CancelToken` at each step, reports `streaming_mode = segmented`, languages `["es"]` and voices `["mock_es"]`
- [X] T014 Implement `src/voxstream/engines/registry.py` selecting an engine by `VOXSTREAM_ENGINE` and raising `UNSUPPORTED_ENGINE` for unknown names (depends on T008, T013)
- [X] T015 [P] Unit tests in `tests/unit/test_config_errors.py`: defaults match T005, env overrides, every `ErrorCode` has a category, error messages contain no path or traceback
- [X] T016 [P] Unit tests in `tests/unit/test_framing.py`: round trip, sequence number wraps are rejected, last-frame flag, short frame rejected
- [X] T017 [P] Unit tests in `tests/unit/test_messages.py`: valid and invalid payload for each message type
- [X] T018 [P] Unit tests in `tests/unit/test_mock_engine.py` and `tests/unit/test_admission.py`: determinism, cancel stops output, injected failure, second acquire raises `BUSY`, release on exception

**Checkpoint**: Foundation ready; user stories can begin

---

## Phase 3: User Story 1 - Stream Spanish speech while text is still arriving (Priority: P1) 🎯 MVP

**Goal**: A client opens a request, streams Spanish text pieces, and receives ordered audio frames
while text is still arriving, then a completion message after end-of-text.

**Independent Test**: With the mock engine, stream a paragraph in small pieces and verify the first
audio frame arrives before the last piece is sent, sequence numbers are continuous, and
`completed` follows `end`. Repeat with Kokoro when models are present.

### Tests for User Story 1

> Write these first and confirm they fail before implementing

- [X] T019 [P] [US1] Unit tests for the segmenter in `tests/unit/test_segmenter.py`: emits at `. ! ? … ;` and newline followed by whitespace or end; no split on `Sr.`, `Sra.`, `Dr.`, `Dra.`, `etc.`, `pág.`, decimals like `3.5`, or ellipsis inside a number; pieces that split a word or sentence mid-way; fallback cut at the last comma or space when pending text reaches `max_pending_chars` (default 120); flush of unterminated remainder at end-of-text; concatenated segments equal the input with whitespace normalized; also cases for mixed-in English words, accented characters and `ñ`, and pieces that split an accented word
- [X] T020 [P] [US1] Unit tests for the session pipeline in `tests/unit/test_session.py` using the mock engine: segments are synthesized in text order, sequence numbers continuous from 0 across segments, frames sliced to `frame_ms`, last-frame flag only on the final frame, first frame produced before `end` when a sentence completed, whole text in one piece still streams by segment
- [X] T021 [P] [US1] Contract test in `tests/contract/test_stream_flow.py` (parametrized over an `engine` fixture, mock first): `start` → `started` descriptor → `text` pieces → `end` → binary frames → exactly one `completed`; descriptor sufficient to decode frames; default voice reported when omitted
- [X] T022 [P] [US1] Integration test in `tests/integration/test_ws_streaming.py`: run a real server on an ephemeral localhost port with the mock engine and a client that sends pieces with short pauses; assert audio arrives before the final piece is sent (SC-010) and that streaming the same text in one piece gives the same spoken text; use the Spanish reference fixtures
- [X] T023 [P] [US1] Integration test in `tests/integration/test_backpressure.py`: a client that stops reading must not make buffered audio exceed `audio_queue_frames` and pending text must stay bounded (SC-005)

### Implementation for User Story 1

- [X] T024 [P] [US1] Implement the incremental Spanish segmenter in `src/voxstream/core/segmenter.py` (`push(text) -> list[Segment]`, `flush() -> list[Segment]`; `Segment` has `index`, `text`, `reason` in `sentence_end|fallback_length|end_of_text`) with the Spanish abbreviation list and fallback rule from research R-06
- [X] T025 [US1] Implement the per-request pipeline in `src/voxstream/core/session.py`: receiver feeds the segmenter, synthesizer task calls `engine.synthesize` per segment and converts blocks to frames of `frame_ms`, sender task writes frames; bounded queues (`audio_queue_frames`, pending text bounded by `max_pending_chars` plus the 2000-character total limit); records `RequestTiming`; state machine `OPEN → ENDING → COMPLETED` per data-model.md; releases the admission slot on every terminal state (depends on T008–T012, T024)
- [X] T026 [US1] Implement the WebSocket server in `src/voxstream/transports/websocket/server.py`: route `/v1/stream`, JSON text frames for control and binary frames for audio, handle `start`, `text`, `end`; assign a UUID request id and send `started`; send `completed` with `audio_frames`, `audio_ms`, `chars`, `timing`; bind to `settings.host` (default `127.0.0.1`) (depends on T025); acquire the admission slot (T010) at `start` and release it on every terminal state, rejecting a `start` beyond the limit with `BUSY`
- [X] T027 [US1] Add plain-HTTP `GET /healthz` (200 when alive) and `GET /readyz` (200 or 503 with JSON reason and the execution provider) to `src/voxstream/transports/websocket/server.py` using the library's request hook
- [X] T028 [US1] Implement `src/voxstream/cli.py` with `voxstream serve` (loads settings, selects engine through the registry, starts the server, graceful shutdown calls `engine.stop()`) and wire `[project.scripts]` (depends on T014, T026)
- [X] T029 [US1] Spike: install `kokoro-onnx` on the target Mac under Python 3.12, download `kokoro-v1.0.onnx` and `voices-v1.0.bin` from the project's `model-files-v1.1` release, confirm that language code `es` and voices `ef_dora`, `em_alex`, `em_santa` synthesize Spanish and that the phonemizer (espeak-ng) works on macOS arm64; record the findings and file sizes in `specs/001-kokoro-websocket-streaming/research.md` under a new "Spike results" heading
- [X] T030 [US1] Implement `voxstream download-models` in `src/voxstream/cli.py` that fetches the two model files into `models/` from the documented release URLs and writes their SHA-256 values to `models/CHECKSUMS.txt`
- [X] T031 [US1] Implement the Kokoro adapter in `src/voxstream/engines/kokoro/engine.py`: lazy model load on first use (or at start when configured), `synthesize` runs inference in a worker thread and yields int16 AudioBlocks at 24 kHz, reads the execution provider from the ONNX session, reports `streaming_mode = segmented`, maps memory exhaustion to `OutOfMemoryError` and load failure to `EngineUnavailableError` with an actionable message, `stop()` is idempotent (depends on T029, T008)
- [X] T032 [P] [US1] Add `src/voxstream/engines/kokoro/voices.py` with the candidate Spanish voice list (`ef_dora`, `em_alex`, `em_santa`), language `es`, and registration of the Kokoro engine in `src/voxstream/engines/registry.py` (the static list is temporary and is replaced by the verification gate in T041; it MUST NOT be served to clients except in the T034 spike)
- [X] T033 [P] [US1] Write `examples/ws_client.py`: connects, sends `start`, streams the given Spanish text in small pieces with short pauses when `--simulate-llm` is set, writes received PCM to a `.wav` file, prints time to first audio and the `completed` message, supports `--voice` and `--cancel-after-chunks N`
- [X] T034 [US1] Spike-only run, using an explicit `--allow-unverified-voices` setting that is off by default and removed or kept disabled once T041 lands: run the Kokoro-backed run of the contract test T021 (marker `model`) and the quickstart step 4; record time to first audio and real-time factor for a ~300-character Spanish paragraph in `specs/001-kokoro-websocket-streaming/research.md` under "Spike results"

**Checkpoint**: User Story 1 works end to end with the mock engine and, when models are present, with Kokoro

---

## Phase 4: User Story 4 - Verify the model and voices produce Spanish (Priority: P1)

**Goal**: A repeatable check that gates which Kokoro voices the service exposes.

**Independent Test**: Run `voxstream verify-voices` against a fake recognizer in tests and against
the real recognizer with the `model` marker; confirm per-voice pass/fail, a stored result with the
model checksum, and that failed voices are hidden.

### Tests for User Story 4

- [X] T035 [P] [US4] Unit tests in `tests/unit/test_verification.py` with a fake synthesizer and fake recognizer: WER normalization (case, punctuation, accents folded for comparison only), pass rule (mean WER ≤ 0.15 and no sentence WER above 0.35), JSON result shape matches data-model.md
- [X] T036 [P] [US4] Unit tests in `tests/unit/test_voice_gate.py`: voice exposed only if `passed` is true and `model.sha256` equals the installed model checksum; mismatched checksum or missing file hides all voices; no verified voice makes `/readyz` return 503 with an actionable reason; missing manual sign-off yields a warning but does not hide the voice
- [X] T037 [P] [US4] Model-marked test in `tests/integration/test_verify_real.py` (marker `model`): run the real verification for one voice and assert a result file is produced

### Implementation for User Story 4

- [X] T038 [P] [US4] Create the fixed reference set `verification/reference_sentences_es.txt` with at least 10 Spanish sentences covering accents, `ñ`, inverted punctuation, numbers and abbreviations
- [X] T039 [US4] Implement `src/voxstream/verification/spanish.py`: synthesize each reference sentence per candidate voice, transcribe with `faster-whisper` (model `small`, language forced to `es`, CPU), normalize, compute WER with `jiwer`, apply the thresholds (configurable), and write `verification/voice-verification.json` in the data-model.md shape including `model.sha256`, recognizer name, per-sentence results and `generated_at`
- [X] T040 [US4] Add `voxstream verify-voices [--voices ...] [--signoff VOICE]` to `src/voxstream/cli.py`; `--signoff` records `manual_signoff` `{by, date}` for a voice that already passed
- [X] T041 [US4] Implement the voice gate in `src/voxstream/engines/kokoro/voices.py` (replace the static list from T032): load the verification file, compare the model checksum, return only passing voices; Kokoro capabilities expose only those voices; keep the recognizer import inside the verification module only so serving never needs it
- [X] T042 [US4] Make `/readyz` honor the gate: when no verified voice exists return 503 with an actionable reason and the execution provider (the `UNSUPPORTED_VOICE` and `ENGINE_UNAVAILABLE` checks at `start` are implemented once, in T053) in `src/voxstream/transports/websocket/server.py` (depends on T027, T041)
- [X] T043 [US4] Run the real verification on the target Mac for all three candidate voices, perform the manual listen, record sign-offs, and commit `verification/voice-verification.json`; if no voice passes, stop and report that a different Spanish-capable model must be selected (blocks shipping, spec assumption)

**Checkpoint**: Only verified Spanish voices are offered; US1 and US4 together form the shippable MVP

---

## Phase 5: User Story 2 - Cancel an in-progress stream (Priority: P2)

**Goal**: Cancel or disconnect stops generation and delivery promptly and frees the service.

**Independent Test**: Start a request, cancel after the first frame, and verify no further frames,
a `cancelled` message, and that a new request is accepted immediately; repeat with a dropped
connection.

### Tests for User Story 2

- [X] T044 [P] [US2] Contract tests in `tests/contract/test_cancel.py`: cancel after first frame yields no later frames and exactly one `cancelled`; text and `end` after cancel are ignored; new `start` succeeds afterwards; cancel racing completion yields either `completed` or `cancelled`, never both
- [X] T045 [P] [US2] Integration test in `tests/integration/test_disconnect.py`: abrupt disconnect during synthesis cancels the engine task, releases the admission slot and leaves no running tasks
- [X] T046 [P] [US2] Model-marked test in `tests/integration/test_cancel_latency.py` (marker `model`): with Kokoro, audio stops within 500 ms of `cancel` (SC-004); record the measured value

### Implementation for User Story 2

- [X] T047 [US2] Add cancellation to `src/voxstream/core/session.py`: shared `CancelToken` passed to `engine.synthesize`, cancel of synthesizer and sender tasks, drop of audio produced after cancel, single terminal `cancelled` message with `audio_frames_sent`, resources released deterministically
- [X] T048 [US2] Handle the `cancel` message and connection close in `src/voxstream/transports/websocket/server.py` (disconnect cancels without sending); on `cancel` for a mismatched id respond `REQUEST_MISMATCH`
- [X] T049 [US2] Document and implement the Kokoro cancellation granularity in `src/voxstream/engines/kokoro/engine.py` (stop before the next inference call; discard in-flight result); if T046 shows more than 500 ms, reduce the fallback segment length cap and record the trade-off

**Checkpoint**: Cancel and disconnect behave per spec

---

## Phase 6: User Story 3 - Receive clear, structured errors (Priority: P2)

**Goal**: Every failure class produces a stable, structured error and the stream state is
unambiguous.

**Independent Test**: Trigger each error code in `contracts/websocket-protocol.md` and verify the
payload shape, that the connection stays usable where specified, and that no internal detail leaks.

### Tests for User Story 3

- [X] T050 [P] [US3] Parametrized contract tests in `tests/contract/test_errors.py`: one case per code (`MALFORMED_MESSAGE`, `NO_ACTIVE_REQUEST`, `REQUEST_MISMATCH`, `BUSY` for second `start` on a connection and from a second connection, `UNSUPPORTED_LANGUAGE`, `UNSUPPORTED_VOICE`, `UNSUPPORTED_ENGINE`, `TEXT_TOO_LONG`, `EMPTY_REQUEST`, `IDLE_TIMEOUT`, `REQUEST_TIMEOUT`, `ENGINE_FAILURE`, `ENGINE_UNAVAILABLE`, `OUT_OF_MEMORY`); each asserts code, category, `retryable`, request_id presence and absence of paths or tracebacks
- [X] T051 [P] [US3] Contract tests in `tests/contract/test_text_limit.py`: total text exactly 2000 characters succeeds, the piece that crosses 2000 ends the request with `TEXT_TOO_LONG` while already-sent audio remains valid and further text is rejected
- [X] T052 [P] [US3] Unit test in `tests/unit/test_error_mapping.py`: engine exceptions and `MemoryError` map to `ENGINE_FAILURE` / `OUT_OF_MEMORY`, unexpected exceptions to `INTERNAL_ERROR` with a generic message

### Implementation for User Story 3

- [X] T053 [US3] Implement request validation in `src/voxstream/transports/websocket/server.py` and `src/voxstream/core/session.py`: language must be `es`, voice must be verified, engine must exist, running character total checked against `max_text_chars` (default 2000), `end` with no text → `EMPTY_REQUEST`, `text` with no open request or in `ENDING` → `NO_ACTIVE_REQUEST`, id mismatch → `REQUEST_MISMATCH`; a requested engine other than the configured engine → `UNSUPPORTED_ENGINE`; this task owns the `UNSUPPORTED_VOICE` and `ENGINE_UNAVAILABLE` checks at `start`
- [X] T054 [US3] Add the `BUSY` rules and tests on top of the admission wiring from T026: a second `start` on the same connection and a `start` from a second connection while the service limit (default 1) is reached are rejected with `BUSY` without touching the active stream (FR-026)
- [X] T055 [US3] Implement the idle timeout (`idle_timeout_s`, speaks pending complete segments first, then `IDLE_TIMEOUT`) and the overall `request_timeout_s` in `src/voxstream/core/session.py`
- [X] T056 [US3] Implement the central exception-to-`error` mapping in `src/voxstream/transports/websocket/server.py` so a failed engine, memory exhaustion or unexpected exception ends the stream with exactly one `error` message distinct from `completed`, and logs details (without text) server-side only

**Checkpoint**: All error classes reproduce deterministically

---

## Phase 7: User Story 5 - Swap engines through a common interface (Priority: P3)

**Goal**: Engines are selected by configuration and the same tests pass on both engines.

**Independent Test**: Run the contract suite with `engine=mock` and `engine=kokoro` and get the same
results; ask for capabilities and read streaming mode.

### Tests for User Story 5

- [X] T057 [P] [US5] Contract test in `tests/contract/test_capabilities.py`: `capabilities` returns languages, verified voices, audio format, `streaming_mode`, `supports_cancel` and `execution_provider`; Kokoro reports `segmented`
- [X] T058 [P] [US5] Make the `engine` fixture in `tests/contract/conftest.py` parametrized over `mock` and `kokoro` (Kokoro param marked `model`), and verify `tests/contract/` runs unchanged for both (SC-008)
- [X] T059 [P] [US5] Unit test in `tests/unit/test_registry.py`: unknown engine name raises `UNSUPPORTED_ENGINE` with an actionable message; selecting an engine changes no transport code path

### Implementation for User Story 5

- [X] T060 [US5] Handle the `capabilities` message in `src/voxstream/transports/websocket/server.py` (allowed only when no request is active) and include the same fields in `/readyz`
- [X] T061 [P] [US5] Write `docs/engines/kokoro.md` documenting languages, verified voices, audio format, runtime requirements, observed memory, streaming mode, cancellation granularity, initialization and shutdown behavior (Principle II and VII), and `docs/engines/adding-an-engine.md` describing the adapter checklist

**Checkpoint**: Engine swap is a configuration change

---

## Phase 8: Polish & Cross-Cutting Concerns

**Purpose**: Constitution obligations that span stories

- [X] T062 [P] Add `tests/unit/test_logging_privacy.py`: logs for a full request contain the request id and stage names but never the input text or audio bytes (FR-023)
- [X] T063 [P] Add `tests/unit/test_security_defaults.py`: default host is `127.0.0.1`, and binding elsewhere requires an explicit setting (FR-022)
- [X] T064 [P] Write `scripts/measure_stream.py` to run repeated warm and cold trials and report median and p95 for time to first audio, real-time factor, inter-frame delay, CPU and peak memory, separating generation from delivery time; run it for SC-001, SC-002, SC-009 (20 consecutive requests) and record results with hardware and versions in `docs/measurements.md`; use Spanish text only, and report peak process memory against the 4 GB ceiling in SC-009
- [X] T065 Evaluate the Core ML execution provider with `scripts/eval_providers.py` (correctness via the verification WER, latency, memory) and record the CPU versus Core ML decision and rationale in `docs/decisions.md`; keep CPU as the default unless Core ML is correct, faster, and within memory
- [X] T066 [P] Write `docs/decisions.md` entries for choices that affect benchmarking: segmentation rules and fallback length, 100 ms frame size, queue bounds, PCM format, concurrency of 1
- [X] T067 Complete `README.md`: install, config table of `VOXSTREAM_*` variables, running, protocol summary linking to `specs/001-kokoro-websocket-streaming/contracts/`, client example, troubleshooting (missing models, not-ready service, espeak issues, out of memory), supported macOS and Python versions, and a "Tested versus planned" section; note that gRPC client examples are delivered with the gRPC feature
- [X] T068 Add a single command `scripts/check.sh` running `ruff check`, `ruff format --check`, `mypy src`, and `pytest`, and confirm it passes
- [X] T069 Walk through every step of `specs/001-kokoro-websocket-streaming/quickstart.md` on the target Mac and fix any step that does not work as written
- [X] T070 Measure the full-precision and quantized Kokoro model files for peak memory, time to first audio, and verification word error rate; record in `docs/decisions.md` which variant is the default and which variants are unsuitable for the 16 GB target (Principle V)

---

## Dependencies & Execution Order

### Phase dependencies

- **Setup (Phase 1)** → **Foundational (Phase 2)** → all user stories → **Polish (Phase 8)**.
- **US1 (Phase 3)** needs Phase 2 only. T029 (Kokoro spike) can start as soon as T001 is done and should be run early because it de-risks everything Kokoro-related.
- **US4 (Phase 4)** needs T031 (Kokoro adapter) and T030 (models). T043 may fail the whole feature, so run it as early as T031 allows.
- **US2 (Phase 5)** needs the session and server from US1.
- **US3 (Phase 6)** needs the session and server from US1; some validation depends on the gate from US4 (T041).
- **US5 (Phase 7)** needs US1 and, for the Kokoro parametrization, US4.

### Within a story

Tests first (they must fail), then segmenter/models, then session, then server and CLI, then
engine-specific work and measurements.

### Parallel opportunities

- Phase 1: T002, T003, T004 in parallel after T001.
- Phase 2: T005–T013 are independent files; T015–T018 can run once their targets exist.
- US1: T019–T023 together; T024, T032, T033 in parallel; T029 can run during Phase 2.
- US4: T035–T038 together.
- After US1: US2, US3 and US5 can proceed in parallel if two developers are available (they touch `session.py`/`server.py`, so sequence those edits).

### Parallel example: User Story 1 tests

```text
T019 tests/unit/test_segmenter.py
T020 tests/unit/test_session.py
T021 tests/contract/test_stream_flow.py
T022 tests/integration/test_ws_streaming.py
T023 tests/integration/test_backpressure.py
```

## Implementation Strategy

### MVP first (US1 + US4)

1. Phases 1–2, then run the Kokoro spike T029 immediately.
2. US1 with the mock engine, then the Kokoro adapter (T030–T034).
3. US4 (verification and gate). If T043 fails, stop and choose another Spanish-capable model before
   any further work.
4. Validate with the quickstart; this is the shippable MVP.

### Incremental delivery

Then add US2 (cancel), US3 (errors), US5 (engine swap and capabilities), and finish with Phase 8
measurements and documentation. Each phase leaves the service runnable and tests green.

## Notes

- `[P]` tasks touch different files with no dependency on unfinished work.
- Commit after each task or logical group; run `scripts/check.sh` before merging a story.
- Do not load Kokoro or the recognizer in default tests; use the mock engine and the `model` marker.
