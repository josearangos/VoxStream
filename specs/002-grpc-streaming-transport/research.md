# Research: gRPC Streaming Transport with WebSocket Parity

No `NEEDS CLARIFICATION` markers remain. Items marked **Unverified** must be confirmed on the
target machine during implementation (tracked as tasks).

## R-01 Call shape

- **Decision**: One bidirectional streaming RPC, `Stream(stream ClientEvent) returns (stream
  ServerEvent)`, one request per call (clarified). A separate unary `GetCapabilities`.
- **Rationale**: Text must flow up while audio flows down, which is exactly bidirectional
  streaming. One request per call makes cancel = cancel the call, and removes request-id
  multiplexing. A unary capabilities call needs no active request, so it is simpler than the
  WebSocket rule "only when no request is active".
- **Alternatives**: Client-streaming text + separate server-streaming audio call (two calls to
  correlate, breaks "one request"); unary request with full text (violates streamed-text story).

## R-02 Application events vs gRPC status

- **Decision**: Terminal outcomes and errors are application events (`Completed`, `Cancelled`,
  `Error` with the same `code`, `category`, `message`, `retryable`) inside the stream. The call then
  ends with gRPC status `OK`. Non-OK status is reserved for transport faults (client cancelled the
  call, deadline, server shutting down).
- **Rationale**: Keeps error codes identical to WebSocket (FR-006) and testable by one suite;
  mapping to gRPC status codes would lose `retryable`/category and diverge between transports.
- **Alternatives**: Map codes to `grpc.StatusCode` (loses parity, two error vocabularies).

## R-03 Event schema

- **Decision**: `ClientEvent` and `ServerEvent` use `oneof`. Audio is its own `AudioChunk` message
  (`request_id`, `sequence`, `last`, `pcm`), so audio and control are distinguishable by type
  without a binary header. `request_id` is optional on client `text`/`end`/`cancel` (the call
  already scopes the request); if present and different, `REQUEST_MISMATCH` is returned.
- **Rationale**: Native protobuf typing replaces the WebSocket 21-byte header and JSON/binary frame
  split while carrying identical fields.

## R-04 Backpressure

- **Decision**: Inbound: the handler reads one `ClientEvent` at a time and awaits
  `Session.feed`, whose bounded queues stop reading when full; HTTP/2 flow control then stalls the
  client. Outbound: the session's send callback pushes into a small bounded queue
  (`OUTBOX_SIZE = 8`) drained by the handler's async generator; a slow reader blocks the
  generator, the queue fills, and synthesis pauses on the existing audio queue.
- **Rationale**: Same bounded-memory behavior as WebSocket (FR-009) with no extra mechanism.
- **Unverified**: that `grpc.aio` async-generator handlers actually apply write backpressure under a
  deliberately slow client; covered by an integration test that measures queue depth.

## R-05 Cancellation and disconnect

- **Decision**: Explicit `Cancel` event → `Session.cancel()` → `Cancelled` event → call ends `OK`.
  Client cancelling or dropping the call surfaces as `asyncio.CancelledError` in the handler; a
  `finally` block cancels the session, awaits it, and releases the admission slot, with no event
  sent. Idempotent with the explicit path.
- **Rationale**: Matches WebSocket rules 2 and 3 and clarification Q4.

## R-06 Limits

- **Decision**: `grpc.max_receive_message_length = 64 KiB` (same as WebSocket), text limit and
  timeouts unchanged and enforced by `Session`. A message over the limit is a transport fault (`RESOURCE_EXHAUSTED`, like WebSocket close 1009). A second `Start` inside one call returns `BUSY` without disturbing the first request.
- **Rationale**: Parity of limits (FR-007, FR-009).

## R-07 Shared service layer

- **Decision**: Extract `core/service.py` (`VoxStreamService`) holding `AdmissionController`,
  engine lazy start, `readiness()`, `capabilities()`, and `open_session(...)` that performs the
  engine/language/readiness/voice/default-voice/admission checks currently inline in
  `VoxStreamServer._on_start`. Both transports call it and own only wire handling.
- **Rationale**: Single source of truth for validation and for the service-wide concurrency limit
  across transports (FR-008). Prevents the two transports from drifting.
- **Alternatives**: Duplicate the logic in the gRPC server (rejected: drift, violates Principle
  III parity); make gRPC call into the WebSocket server (rejected: couples transports).

## R-08 Transport-neutral frames

- **Decision**: `Session` receives `send_audio(frame: AudioFrame)` where `AudioFrame` is a plain
  dataclass in `core/frames.py`. The WebSocket adapter wraps it with `encode_frame`; the gRPC
  adapter converts it to `AudioChunk`. The last-frame terminator (empty payload, `last=True`) is
  preserved on both.
- **Rationale**: Removes today's `core` → `transports.websocket.framing` import so core is truly
  transport-free. Existing frame tests keep passing.

## R-09 Health when WebSocket is disabled

- **Decision**: Keep `/healthz` and `/readyz` on the WebSocket port when WebSocket is enabled
  (unchanged). When it is disabled, start a minimal asyncio HTTP listener on `port` serving only
  those two paths (`transports/health.py`). No gRPC health protocol (clarified).
- **Rationale**: One probe method (`curl`) for operators regardless of transports.
- **Alternatives**: `grpc.health.v1` (clarified away); always-on separate health port (extra
  configuration for no gain).

## R-10 Defaults and configuration

- **Decision**: `enable_websocket=True`, `enable_grpc=True` (clarified), `grpc_port=50051` (gRPC
  convention; distinct from 8765), shared `host`. Starting with both disabled is a configuration
  error with an actionable message. Non-local bind requires the existing opt-in for either.
- **Env**: `VOXSTREAM_ENABLE_WEBSOCKET`, `VOXSTREAM_ENABLE_GRPC`, `VOXSTREAM_GRPC_PORT`.

## R-11 Dependencies and code generation

- **Decision**: Runtime `grpcio` + `protobuf` (declared); dev `grpcio-tools`. Stubs generated by
  `scripts/gen_proto.sh` from `proto/voxstream/v1/voxstream.proto` and committed under
  `transports/grpc/gen/`. Generated files excluded from `ruff` and `mypy`; `grpc.*` added to mypy
  `ignore_missing_imports`. A test fails if the committed stubs are older than the `.proto`.
- **Rationale**: Users do not need the compiler to run the service; stubs stay reproducible.
- **Unverified**: generated code's minimum `protobuf` runtime vs the locked version; pin
  `protobuf` in `pyproject.toml` to the version the stubs were generated with.

## R-12 Observability

- **Decision**: Add a `transport` field (`websocket` | `grpc`) to the log context only (not
  in `RequestTiming`, whose values must stay numeric for the gRPC `Completed.timing` map) so
  generation time and delivery time can be separated per transport in the logs. No new metrics
  system.

## R-13 Contract-test strategy

- **Decision**: Introduce a transport-neutral test client (`start/text/end/cancel/collect`
  returning frames and normalized control dicts) with `WsClient` and `GrpcClient`
  implementations, and a `transport` pytest parameter next to `engine_name`. WebSocket-only wire
  tests (invalid JSON, binary from client) stay in WebSocket-specific files; gRPC-only wire tests
  cover oversize message and call cancellation.
- **Rationale**: One expectation set, two transports (SC-001, SC-002).

## R-14 Open risks

| Risk | Mitigation |
|------|------------|
| `Session` refactor regresses WebSocket | Land it first with the existing suite unchanged and green |
| grpc.aio write backpressure not effective | Integration test with slow reader; fallback to explicit credit counter |
| Stub/protobuf version mismatch | Pin protobuf; regeneration script; stale-stub test |
| Port 50051 already in use | Startup fails with actionable error naming the port and env var |
