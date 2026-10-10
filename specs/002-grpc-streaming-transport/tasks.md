---

description: "Task list for gRPC Streaming Transport with WebSocket Parity"
---

# Tasks: gRPC Streaming Transport with WebSocket Parity

**Input**: Design documents from `/specs/002-grpc-streaming-transport/`

**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/ (all present)

**Tests**: Included. Constitution Principle IX requires unit, contract and integration tests with a
mock engine; Principle III requires one shared contract suite for both transports. Tests that load
Kokoro carry the existing pytest marker `model` and are excluded from the default run.

**Organization**: Grouped by user story. Paths are relative to the repository root
(`/Users/josearangos/Documents/Study/VoxStream`).

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependency on an incomplete task)
- **[Story]**: US1–US4 map to the user stories in spec.md

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Dependencies, schema and generated stubs

- [X] T001 Add runtime dependencies `grpcio` and `protobuf` and dev dependency `grpcio-tools` to `pyproject.toml`, then run `uv lock`; after T003 pins the generated stub version, constrain `protobuf` in `pyproject.toml` to a range that includes the version the stubs were generated against (research R-11)
- [X] T002 [P] Copy `specs/002-grpc-streaming-transport/contracts/voxstream.proto` to `proto/voxstream/v1/voxstream.proto` unchanged (package `voxstream.v1`, service `Synthesizer` with `Stream` bidirectional and `GetCapabilities` unary)
- [X] T003 Create `scripts/gen_proto.sh` that runs `uv run python -m grpc_tools.protoc -Iproto/voxstream/v1 --python_out=src/voxstream/transports/grpc/gen --grpc_python_out=src/voxstream/transports/grpc/gen --pyi_out=src/voxstream/transports/grpc/gen voxstream.proto` so the output is flat in `gen/` (never `gen/voxstream/v1/`, which would shadow the real `voxstream` package), rewrites the generated `import voxstream_pb2 as ...` in `voxstream_pb2_grpc.py` to `from . import voxstream_pb2 as ...`, and creates `gen/__init__.py`; the `.proto` stays at `proto/voxstream/v1/voxstream.proto` so the wire package remains `voxstream.v1`; run it and commit the generated files (depends on T001, T002)
- [X] T004 [P] Create package skeleton `src/voxstream/transports/grpc/__init__.py` (empty) and exclude `src/voxstream/transports/grpc/gen/` from `ruff` (`extend-exclude`) and `mypy` (`exclude`) in `pyproject.toml`; add `grpc.*` and `google.protobuf.*` to the mypy `ignore_missing_imports` override

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Make `core` transport-free and extract the shared service layer. The existing
WebSocket suite MUST stay green and unchanged in behavior after every task in this phase.

**⚠️ CRITICAL**: No user story work can begin until this phase is complete

- [X] T005 Run `scripts/check.sh` on the untouched code and record that it is green; this is the regression baseline for the refactor
- [X] T006 [P] Create `src/voxstream/core/frames.py` with frozen dataclass `AudioFrame(request_id: uuid.UUID, sequence: int, last: bool, pcm: bytes)`; `sequence` is uint32 starting at 0, +1 per frame, continuous across segments; `last` is True only on the empty-payload terminator
- [X] T007 Change `src/voxstream/core/session.py` so `Session` takes `send_audio: Callable[[AudioFrame], Awaitable[None]]` instead of `send_frame` of bytes, builds `AudioFrame` in `_send`, and no longer imports `voxstream.transports.websocket.framing`; keep the terminator behavior (empty payload, `last=True`, sent after final audio) and counters unchanged; update `tests/unit/test_session.py` to assert on `AudioFrame` objects (depends on T006)
- [X] T008 Update `src/voxstream/transports/websocket/server.py` so the callback passed to `Session` converts an `AudioFrame` with `encode_frame(f.request_id, f.sequence, f.pcm, last=f.last)` and sends it; run `uv run pytest` and confirm the whole existing suite passes unchanged (depends on T007)
- [X] T009 Create `src/voxstream/core/service.py` with `VoxStreamService(settings, engine)` owning one `AdmissionController`, the engine lock and lazy-start flag, `readiness()` and `capabilities()` (moved from `VoxStreamServer.readiness` and `_on_capabilities` logic), `ensure_engine()`, and `open_session(engine, voice, language, send_audio) -> OpenedSession` that performs, in this order, the checks currently in `VoxStreamServer._on_start`: engine name (`UNSUPPORTED_ENGINE`), language must be `es` (`UNSUPPORTED_LANGUAGE`), readiness (`ENGINE_UNAVAILABLE`), voice in verified voices (`UNSUPPORTED_VOICE`, message lists available voices), default-voice rule, admission acquire (`BUSY`), engine start; it returns the started-ready `Session` plus a `StreamDescriptor`-equivalent dataclass and a `release()` callable that frees the admission slot exactly once; error codes and messages must be identical to today's (depends on T007)
- [X] T010 Refactor `src/voxstream/transports/websocket/server.py` to delegate to `VoxStreamService` (admission, readiness for `/readyz`, capabilities, `_ensure_engine`, `_on_start` validation) keeping only wire handling; accept an injected `VoxStreamService` instead of building one, and add a minimal `src/voxstream/app.py` `VoxStreamApp(settings, engine)` that builds one service and starts only the WebSocket server (exposes `port`, `admission`, `engine`, `service`, supports `async with`, closes the transport then `engine.stop()` once); set `transport_var` to `websocket` for every WebSocket connection handler; keep its public attributes `port`, `start`, `close`, `serve_forever`; run the full existing suite and confirm it passes unchanged (depends on T008, T009)
- [X] T011 [P] Write `tests/unit/test_service.py` covering `open_session`: each error code in the order above, default voice selection, a second `open_session` at limit 1 raising `BUSY`, `release()` idempotent, slot released if engine start fails (uses `MockEngine`; depends on T009)
- [X] T012 [P] Extend `src/voxstream/config.py` `Settings` with `enable_websocket: bool = True`, `enable_grpc: bool = True`, `grpc_port: int = 50051`, and a `validate_transports()` method raising `ValueError` with an actionable message naming `VOXSTREAM_ENABLE_WEBSOCKET` and `VOXSTREAM_ENABLE_GRPC` when both are false ("At least one of the two transports must be enabled."); `grpc_port` of 0 is allowed (tests, ephemeral) and must be distinct from `port` unless 0; extend `validate_bind()` so it applies to both transports (they share `host`); add cases to `tests/unit/test_config_errors.py` and `tests/unit/test_security_defaults.py`
- [X] T013 [P] Add a `transport` field (`websocket` | `grpc`) to the log context in `src/voxstream/logging.py` (a `transport_var` ContextVar emitted in `JsonFormatter` like `request_id`); `transport` is a log-context field only and MUST NOT be added to `RequestTiming.to_dict()` because the gRPC `Completed.timing` is `map<string,double>`; add assertions to `tests/unit/test_logging_privacy.py` that logs still contain no text or audio and now include `transport`
- [X] T014 Run `scripts/check.sh` and confirm it is green; Phase 2 is complete only when the baseline from T005 is matched

**Checkpoint**: Core has no transport imports; both future transports can share admission, readiness
and validation.

---

## Phase 3: User Story 1 - Stream Spanish speech over gRPC while text is still arriving (Priority: P1) 🎯 MVP

**Goal**: A gRPC client opens a `Stream` call, sends text pieces, and receives `Started`, ordered
audio chunks while text is still arriving, and `Completed`, with the same audio as WebSocket.

**Independent Test**: Run the streamed-text scenario over gRPC with the mock engine: first audio
chunk arrives before the last piece is sent, sequence numbers are continuous, exactly one
`Completed`, and the reassembled bytes equal the WebSocket result for the same text and voice.

### Tests for User Story 1 (write first; they must fail)

- [X] T015 [P] [US1] Write `tests/unit/test_grpc_convert.py` for `src/voxstream/transports/grpc/convert.py`: `AudioFrame` ↔ `AudioChunk` round-trip including the empty-payload `last=True` terminator and sequence up to uint32 max; `SessionResult` → `Completed` (with `timing` map; `None` timing values are dropped so every map value is a double and the map never carries strings) and `Cancelled`; `VoxStreamError` → `Error` carrying `code`, `category`, `message`, `retryable`, and unset `request_id` for a rejected `Start`; `Start` with unset optional fields maps to `None`
- [X] T016 [P] [US1] Write `tests/unit/test_proto_stubs.py`: importing the generated modules works, and the committed stubs are not older than `proto/voxstream/v1/voxstream.proto` (regenerate into a temporary directory with the same command as `scripts/gen_proto.sh` and diff against the committed files; do not compare file mtimes), failing with the message "run scripts/gen_proto.sh"
- [X] T017 [US1] Create the transport-neutral test client in `tests/helpers.py`: keep the existing WebSocket `Client` API, add `GrpcClient` with the same methods (`send(type=..., **kw)`, `recv_json`, `start`, `text`, `end`, `cancel`, `collect`) that opens a `grpc.aio` channel to `127.0.0.1:<grpc_port>`, translates the dict-style `send(type="start"|"text"|"end"|"cancel"|"capabilities")` into `ClientEvent` / `GetCapabilities`, and normalizes `ServerEvent` to the same control dicts (`type` is `started`/`completed`/`cancelled`/`error`/`capabilities`) and `AudioFrame`-like objects the WebSocket client returns; `GrpcClient.recv()` returns `bytes` for an audio chunk and a JSON `str` for every control event, exactly like the WebSocket client, because the existing contract tests rely on that; change `running_server` and `client_for` so the running object is a `VoxStreamApp` (created in T010, gRPC added in T022) exposing `.port`, `.grpc_port`, `.admission`, `.engine`, `.service`, and `.transport`, with `client_for(app)` choosing the client by `app.transport`; grep `tests/` for `server.` attribute uses and adapt them
- [X] T018 [US1] Add a `transport` pytest parameter (`websocket`, `grpc`) to `tests/contract/conftest.py` next to `engine_name`; the `serve` fixture sets `app.transport` from it and starts both transports; run `tests/contract/test_stream_flow.py`, `test_capabilities.py` and `test_text_limit.py` for both transports (they must fail for `grpc` until implemented) (depends on T017)
- [X] T019 [P] [US1] Write `tests/integration/test_grpc_streaming.py`: (a) sends `SPANISH_PIECES` with 50 ms pauses and asserts the first `AudioChunk` arrives before the last text piece is sent (SC-003); (b) default voice used and reported when `Start` omits voice; (c) for the same text and voice, concatenated PCM from gRPC equals concatenated PCM from WebSocket and the `Started` descriptors are equal field by field (SC-002); (d) an oversize `Text` (> 64 KiB) fails the call with `RESOURCE_EXHAUSTED`

### Implementation for User Story 1

- [X] T020 [P] [US1] Implement `src/voxstream/transports/grpc/convert.py` with pure functions between `core` types and the generated messages: `to_audio_chunk(AudioFrame)`, `to_started(request_id, descriptor)`, `to_completed(SessionResult)` (skip `None` timing values), `to_cancelled(SessionResult)`, `to_error(VoxStreamError, request_id | None)`, `capabilities_to_proto(EngineCapabilities)`; audio is `pcm_s16le`, 24000 Hz, 1 channel; no text or audio is logged (depends on T003, T006)
- [X] T021 [US1] Implement `src/voxstream/transports/grpc/server.py`: class `GrpcServer(service, settings)` using `grpc.aio.server` with options `grpc.max_receive_message_length = 64 * 1024` and `grpc.max_send_message_length` large enough for one `frame_ms` chunk; servicer `Synthesizer` with `Stream` (async generator handler) that reads the first event, requires `Start`, calls `service.open_session(...)`, yields `Started`, starts the session, then concurrently (a) reads inbound events and awaits `session.feed` / `session.end` (reading one event at a time gives HTTP/2 backpressure) and (b) drains a bounded outbound `asyncio.Queue` with `OUTBOX_SIZE = 8` fed by the session's `send_audio` and by the terminal watcher, yielding `AudioChunk` then exactly one `Completed`/`Cancelled`/`Error`, then ends the call with status OK; `finally` cancels the session, awaits it and calls `release()`; `GetCapabilities` unary returns `capabilities_to_proto`; set `transport_var` to `grpc` per call; `start()` binds `settings.host:settings.grpc_port` (after `validate_bind`), exposes `port` (the actual bound port when 0), `close()` stops the server with a short grace and calls no engine stop (the app owns that) (depends on T009, T020)
- [X] T022 [US1] Extend `src/voxstream/app.py` (created in T010) so `VoxStreamApp` also starts `GrpcServer` per `enable_websocket` / `enable_grpc` (both default true), exposes `grpc_port`, calls `settings.validate_transports()` and `validate_bind()` first, and on `close()` closes both transports then `engine.stop()` once (depends on T010, T012, T021)
- [X] T023 [US1] Update `src/voxstream/cli.py` `_serve` to use `VoxStreamApp` and print one line per enabled endpoint (`WebSocket ws://HOST:PORT/v1/stream`, `gRPC HOST:GRPC_PORT`); catch `ValueError` from validation and exit 2 with the message; fail with an actionable error naming `VOXSTREAM_GRPC_PORT` when the gRPC port is already in use (depends on T022); add `tests/integration/test_grpc_port_in_use.py` that occupies the port and asserts the startup error names `VOXSTREAM_GRPC_PORT`
- [X] T024 [US1] Make the US1 tests pass: run `uv run pytest tests/contract tests/integration/test_grpc_streaming.py tests/unit/test_grpc_convert.py tests/unit/test_proto_stubs.py` and fix until green for both transports; confirm the WebSocket results are unchanged (depends on T018, T019, T021, T022)

**Checkpoint**: gRPC streams Spanish audio end to end and matches WebSocket output. This is the MVP.

---

## Phase 4: User Story 2 - Cancel, disconnect, and receive structured errors (Priority: P2)

**Goal**: Cancellation, call drop, backpressure and every error code behave over gRPC exactly as
over WebSocket.

**Independent Test**: The existing cancel/error/limit contract tests pass for the `grpc`
parameter with the same expectations, plus gRPC-only tests for call cancellation and oversize
messages.

### Tests for User Story 2 (write first; they must fail)

- [X] T025 [US2] Enable the `grpc` transport parameter for `tests/contract/test_cancel.py` and `tests/contract/test_errors.py`; where a test is WebSocket-wire-specific (invalid JSON text, binary frame from client) move it to `tests/integration/test_ws_wire_errors.py` and add the gRPC equivalents there as noted below, keeping every error-code expectation identical
- [X] T026 [P] [US2] Write `tests/integration/test_grpc_wire_errors.py`: event with no case set → `MALFORMED_MESSAGE` and call stays usable; `Text`/`End`/`Cancel` before `Start` → `NO_ACTIVE_REQUEST`; `request_id` present and wrong → `REQUEST_MISMATCH` and request continues; `Text` after `End` → `NO_ACTIVE_REQUEST` and request still `Completed`; a second `End` is ignored and the request still completes once; second `Start` in one call → `BUSY` and first request unaffected; rejected `Start` (bad voice / language / engine) → `Error` with no `request_id`, call ends OK
- [X] T027 [P] [US2] Write `tests/integration/test_grpc_cancel_disconnect.py`: explicit `Cancel` stops audio within 500 ms and yields exactly one `Cancelled` (also for a cancel racing completion: `Completed` or `Cancelled`, never both); cancelling the client call (`call.cancel()`) and dropping the channel both release the admission slot (a new request then succeeds, `admission.active == 0`) with no leaked tasks; audio never follows a terminal event
- [X] T028 [P] [US2] Write `tests/integration/test_grpc_backpressure.py`: a client that reads one chunk then sleeps while the engine produces many segments; assert the pending-text buffer stays within `max_pending_chars` plus the segment queue bound while the client stalls (FR-009), and outbound queue depth never exceeds `OUTBOX_SIZE` plus `audio_queue_frames`, synthesis pauses, and process memory stays bounded; this verifies research R-04 and, if write backpressure is not applied by `grpc.aio`, the task fails and T031 must add an explicit credit counter
- [X] T029 [P] [US2] Write `tests/integration/test_grpc_timeouts.py`: no text or `End` within `idle_timeout_s` → `IDLE_TIMEOUT` after pending complete segments are spoken; request longer than `request_timeout_s` → `REQUEST_TIMEOUT`; text over `max_text_chars` mid-stream → `TEXT_TOO_LONG`; `End` with no text → `EMPTY_REQUEST`; engine failure injected at segment N → `ENGINE_FAILURE`

### Implementation for User Story 2

- [X] T030 [US2] Complete event handling in `src/voxstream/transports/grpc/server.py`: unset oneof → `MALFORMED_MESSAGE` (non-terminal); `Text`/`End`/`Cancel` before `Start` and `Text` after `End` → `NO_ACTIVE_REQUEST`; optional `request_id` mismatch → `REQUEST_MISMATCH`; second `Start` → `BUSY` without touching the first session; `TEXT_TOO_LONG` and `EMPTY_REQUEST` fail the session via `session.fail(err)` exactly like `VoxStreamServer._on_text_or_end`; map every exception with `map_exception` so messages never contain stack traces, paths or input text
- [X] T031 [US2] Implement cancellation in `src/voxstream/transports/grpc/server.py`: `Cancel` handled immediately (never queued behind text) → `session.cancel()` → `Cancelled` event → OK; call cancellation / `asyncio.CancelledError` / client disconnect → cancel session, await it, release slot, send nothing; make both paths idempotent; if T028 shows missing write backpressure, add an explicit bounded credit counter between the session callback and the generator (depends on T030)
- [X] T032 [US2] Run `uv run pytest` and fix until T025–T029 pass for both transports with identical expectations (SC-001, SC-004); run `uv run pytest -m model tests/contract` once with Kokoro if models are installed

**Checkpoint**: gRPC cancellation, errors, timeouts and backpressure match WebSocket.

---

## Phase 5: User Story 3 - Run both transports and select them by configuration (Priority: P2)

**Goal**: WebSocket, gRPC or both from configuration only, with one shared engine, one concurrency
limit and one health/readiness source.

**Independent Test**: Start with only gRPC, only WebSocket, and both; each enabled transport
serves a request, a disabled one refuses connections, `/readyz` answers in all three, and a
request on one transport makes the other return `BUSY`.

### Tests for User Story 3 (write first; they must fail)

- [X] T033 [P] [US3] Write `tests/integration/test_both_transports.py`: default `Settings` enables both (assert `enable_websocket` and `enable_grpc` are true); with limit 1, an active WebSocket request makes a gRPC `Start` return `BUSY`, and the reverse; only one engine instance is started (assert `engine.start` called once); closing the app stops both listeners and the engine once
- [X] T034 [P] [US3] Write `tests/integration/test_transport_selection.py`: `enable_websocket=false` → WebSocket connection refused, gRPC works, `GET /readyz` on `settings.port` returns the same JSON body as with WebSocket enabled; `enable_grpc=false` → gRPC connection fails, WebSocket works; both false → `ValueError` mentioning both env vars; `/healthz` returns 200 in all valid modes
- [X] T035 [P] [US3] Extend `tests/unit/test_security_defaults.py`: default `host` is `127.0.0.1` and the gRPC server binds only to it; a non-loopback host raises unless `allow_non_local_bind=true`, for gRPC as well as WebSocket (FR-011)

### Implementation for User Story 3

- [X] T036 [US3] Create `src/voxstream/transports/health.py`: `HealthServer(service, host, port)` built on `asyncio.start_server` that answers only `GET /healthz` (200 `ok`) and `GET /readyz` (200 or 503 with the same JSON body as the WebSocket server, from `service.readiness()`), 404 otherwise, with request size and read timeouts so it cannot hang; no other methods or paths (depends on T009)
- [X] T037 [US3] Update `src/voxstream/app.py` so that when `enable_websocket` is false and any other transport is enabled, a `HealthServer` is started on `settings.port`; when WebSocket is enabled the existing `/healthz` and `/readyz` on the WebSocket port are used and no second listener starts; startup logs list the active endpoints and the port clash message names the setting to change (depends on T022, T036)
- [X] T038 [US3] Make the US3 tests pass and confirm that disabling a transport does not import or start its server module (lazy imports in `app.py`), so a WebSocket-only run does not require `grpc` at import time beyond the declared dependency; run `uv run pytest`

**Checkpoint**: Transports are independently selectable and share one limit and one health source.

---

## Phase 6: User Story 4 - Documented gRPC client and contract (Priority: P3)

**Goal**: A developer can read the gRPC contract and run Spanish example clients from the README.

**Independent Test**: Following only the README, run each gRPC example against a running service
and observe the documented output in under 5 minutes.

- [X] T039 [P] [US4] Create `examples/grpc_client.py` mirroring `examples/ws_client.py` flags (`--simulate-llm`, `--voice`, `--output`, `--cancel-after-chunks`, text argument) using the generated stubs, Spanish default text and help strings, printing time to first audio, the `completed` / `cancelled` / `error` event, and saving WAV when `--output` is given; add `--host` and `--port` (default `127.0.0.1:50051`)
- [X] T040 [P] [US4] Copy the final contract documents to the repo docs: add `docs/grpc-protocol.md` (copy of `specs/002-grpc-streaming-transport/contracts/grpc-protocol.md` with relative links fixed) and verify that every WebSocket message and every error code in `specs/001-kokoro-websocket-streaming/contracts/websocket-protocol.md` has a row in the mapping table (SC-008); fix gaps in both copies
- [X] T041 [US4] Update `README.md`: describe two transports, the new settings table rows (`ENABLE_WEBSOCKET` default `true`, `ENABLE_GRPC` default `true`, `GRPC_PORT` default `50051`), the gRPC example commands in Spanish matching quickstart §3–§5, the note that health is HTTP on `PORT` for every mode, that gRPC is plaintext and local-only, regeneration with `scripts/gen_proto.sh`, and extend the "Supported versions" section with the `grpcio`, `grpcio-tools` and `protobuf` versions from `uv.lock`, stating they were tested on macOS arm64 with Python 3.12 (Principle IX); a "tested versus planned" list (gRPC tested with mock and Kokoro; TLS, auth and benchmarks planned)
- [X] T042 [P] [US4] Update `docs/architecture.html` and regenerate `docs/architecture.png` (via the `archify` skill or the same procedure used for the existing diagram) to show both transports feeding the shared service, session, and engine interface; update the architecture paragraph in `README.md` to match
- [X] T043 [P] [US4] Add a short "Transports" section to `docs/decisions.md` recording: one request per call, errors as in-stream events with OK status, committed generated stubs, shared service layer, health on HTTP only, default port 50051 (decisions from research R-01, R-02, R-07, R-09, R-10, R-11)
- [X] T044 [US4] Walk through every step of `specs/002-grpc-streaming-transport/quickstart.md` on the target Mac using only the README where possible, time the run for SC-007, and fix any step that does not work as written (depends on T039, T041)

**Checkpoint**: Contract, examples and README are complete and verified.

---

## Phase 7: Polish & Cross-Cutting Concerns

- [X] T045 [P] Extend `scripts/measure_stream.py` with `--transport {websocket,grpc}` so the same measurement (time to first audio, RTF, per-chunk delivery overhead, peak RSS) runs on either transport using the same text and voice; run 20 consecutive requests per transport and confirm peak process memory stays under 4 GB with no out-of-memory failure (SC-006); record the numbers in `docs/measurements.md` labeled as local-loopback, not remote-network (Principle III); this is a sanity check only, the formal benchmark is the next feature
- [X] T046 [P] Add `examples` and the generated-stub exclusion to `scripts/check.sh` lint paths if missing, and make `scripts/check.sh` fail with "run scripts/gen_proto.sh" when stubs are stale (reuse T016's check)
- [X] T047 [P] Add an integration test `tests/integration/test_logging_transport_label.py` asserting that a gRPC request logs `transport: "grpc"` and a WebSocket request logs `transport: "websocket"`, each with its correlation id at every stage (`segment_synth`, `chunk_sent`, `request_end`) and that no log line contains the input text or audio bytes
- [X] T048 Run the full gate: `scripts/check.sh`, then `uv run pytest -m model` if models are installed; confirm all success criteria SC-001–SC-008 in the table below
- [X] T049 Update `specs/002-grpc-streaming-transport/checklists/requirements.md` only if the spec changed during implementation; re-run `/speckit-analyze` to confirm spec, plan and tasks are consistent

---

## Dependencies & Execution Order

### Phase dependencies

- **Setup (Phase 1)** → **Foundational (Phase 2)** → **US1 (Phase 3)** → US2, US3 → **US4** → **Polish**.
- **Phase 2** blocks everything: T005 baseline first, then T006 → T007 → T008, T009 → T010; T011, T012, T013 are independent; T014 closes the phase.
- **US1 (Phase 3)** needs Phase 2 and the stubs from T003. It is the MVP.
- **US2 (Phase 4)** needs the gRPC server from US1 (T021, T022); its tests are independent files and can be written in parallel.
- **US3 (Phase 5)** needs `VoxStreamApp` from US1 (T022); independent of US2 apart from sharing `server.py` only through the app, so it can proceed in parallel with US2.
- **US4 (Phase 6)** needs US1 working; T044 needs T039 and T041.
- **Polish (Phase 7)** needs all stories.

### Within a story

Tests first (they must fail), then conversion functions, then the server, then app/CLI wiring, then
make the tests pass.

### Parallel opportunities

- Phase 1: T002 and T004 in parallel; T003 after T001/T002.
- Phase 2: T006 early; T011, T012, T013 in parallel once their dependencies exist.
- US1: T015, T016, T019 together; T020 beside the tests; T021 follows T020.
- US2: T026, T027, T028, T029 together (separate files).
- US3: T033, T034, T035 together; T036 beside them.
- US4: T039, T040, T042, T043 together.
- After US1, two developers can take US2 and US3 at the same time (they touch `grpc/server.py` and `app.py`/`health.py` respectively).

## Implementation Strategy

- **MVP**: Phases 1–3 (through T024). Delivers gRPC streaming with output identical to WebSocket.
- **Safety first**: do not start T015 until T014 is green; the refactor must not change WebSocket
  behavior.
- **Incremental delivery**: US2 makes gRPC safe; US3 makes it operable; US4 makes it usable by
  others; Polish confirms the success criteria and prepares the benchmark feature.

## Success Criteria Traceability

| Criterion | Verified by |
|-----------|-------------|
| SC-001 shared contract tests pass for gRPC | T018, T024, T025, T032 |
| SC-002 identical audio over both transports | T019 (c) |
| SC-003 first audio before last piece | T019 (a) |
| SC-004 cancel/disconnect bound | T027, T032 |
| SC-005 cross-transport `BUSY` | T033 |
| SC-006 memory over 20 requests | T045 |
| SC-007 README run under 5 minutes | T044 |
| SC-008 every message and code mapped | T040 |

## Phase 8: Convergence

- [ ] T050 Add a `model`-marked gRPC variant of `tests/integration/test_cancel_latency.py` (Kokoro; audio stops within 500 ms of an explicit `Cancel`) per SC-004 (partial)
- [ ] T051 Add a test that a WebSocket-only run never imports `voxstream.transports.grpc` (and a gRPC-only run never imports `voxstream.transports.websocket`), asserted through `sys.modules` in a subprocess, per plan: lazy transport imports / T038 (partial)
- [ ] T052 Add an integration test where the engine fails mid-stream on one transport while the other transport serves the next request successfully (slot released, engine still usable), per spec Edge Cases (partial)
- [ ] T053 Remove or justify the unused `VoxStreamApp.serve_forever`, `VoxStreamServer.serve_forever` and `GrpcServer.serve_forever` (the CLI waits on a stop event instead), per plan: simplicity, Constitution XI (unrequested)
- [ ] T054 Time the README-only gRPC run (install, `serve`, `examples/grpc_client.py`) on the target Mac with Kokoro and record the result in `docs/measurements.md`, per SC-007 (partial)
- [ ] T055 Re-run `/speckit-analyze` for spec, plan and tasks consistency and record any drift, per T049 (partial)
