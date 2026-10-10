# Feature Specification: gRPC Streaming Transport with WebSocket Parity

**Feature Branch**: `002-grpc-streaming-transport`

**Created**: 2026-10-10

**Status**: Draft

**Input**: User description: "what is the next feature?" — interpreted from the project constitution (Principle III, Principle XIII, Success Criteria 4–5) and the out-of-scope list of feature 001: add the gRPC transport so that VoxStream offers two independent transports with equivalent behavior, the prerequisite for fair transport benchmarking.

## Clarifications

### Session 2026-10-10

- Q: Which transports are enabled by default when the service starts with no transport configuration? → A: Both WebSocket and gRPC, each on localhost only.
- Q: How is health and readiness reported for a gRPC-only deployment? → A: The existing HTTP health/readiness endpoints remain available whenever any transport is enabled; no separate gRPC health check.
- Q: Does one gRPC call carry one request or several in sequence? → A: One request per call; a client opens a new call for each request, and cancelling the call cancels the request.
- Q: How does a gRPC client cancel? → A: Both: an explicit cancel message that receives a "cancelled" confirmation (equivalent to WebSocket), and cancelling or dropping the call also stops the request (treated like a disconnect, no confirmation).

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Stream Spanish speech over gRPC while text is still arriving (Priority: P1)

A client (for example, the language-model stage of a voice agent) connects to the local VoxStream
service over gRPC, opens a request, and sends Spanish text in small pieces as it is produced. As
with the WebSocket transport, the service starts speaking as soon as a speakable segment has
arrived, streams ordered audio back while later text is still arriving, and ends with an explicit
completion message after the client signals end-of-text. Every audio chunk carries enough metadata
(request identifier, sequence number, encoding, sample rate, channels) to be decoded and played.

**Why this priority**: This is the whole purpose of the feature. Without a working gRPC streaming
path there is nothing to compare against WebSocket, and it alone is a viable MVP.

**Independent Test**: Run the same streamed-text client scenario used for WebSocket (a Spanish
paragraph sent in small pieces with short pauses) against the gRPC transport. Verify the first
audio chunk arrives before the last text piece is sent, chunks are ordered, the reassembled audio is
playable, and a completion message ends the stream.

**Acceptance Scenarios**:

1. **Given** the service is ready, **When** a client opens a valid gRPC request, **Then** it
   receives an acknowledgement with a request identifier and the audio format, and can then send
   text pieces.
2. **Given** a request is open, **When** text pieces arrive that complete a first sentence,
   **Then** audio for that sentence starts streaming back before the remaining text has been
   received.
3. **Given** the client has sent end-of-text, **When** all remaining audio has been delivered,
   **Then** the client receives ordered audio chunks followed by a completion message.
4. **Given** a request that omits voice configuration, **When** it is processed, **Then** the
   default Spanish voice is used and the response states which voice was used.
5. **Given** the same Spanish text, voice and engine, **When** it is sent over gRPC and over
   WebSocket, **Then** the reassembled audio is identical in content and format.

---

### User Story 2 - Cancel, disconnect, and receive structured errors (Priority: P2)

A gRPC client can cancel an in-progress request and receives a confirmation; audio stops promptly
and resources are released. If the client drops the connection, generation stops and nothing is
left running. Malformed requests, unsupported or non-Spanish voices, over-limit text, busy service,
timeouts and engine failures are reported as structured errors using the same error codes and
meanings as the WebSocket transport.

**Why this priority**: Equivalent cancellation and error semantics are required for the two
transports to be comparable and for gRPC to be safe to use, but they depend on the P1 stream.

**Independent Test**: Run the shared contract tests for cancellation, disconnect, and every defined
error condition against the gRPC transport and confirm they pass unchanged against the same
expectations used for WebSocket.

**Acceptance Scenarios**:

1. **Given** audio is streaming, **When** the client cancels, **Then** audio stops within the same
   latency bound as WebSocket and the client receives a cancellation confirmation.
2. **Given** audio is streaming, **When** the client disconnects abruptly, **Then** generation
   stops and the request's resources are released.
3. **Given** a request for a non-Spanish or unverified voice, **When** it is opened, **Then** the
   client receives the same structured "unsupported voice" error code as over WebSocket.
4. **Given** one request is active and the concurrency limit is reached, **When** another client
   opens a request on either transport, **Then** it receives a structured "busy" error.
5. **Given** a slow client, **When** it reads audio slower than it is produced, **Then** buffered
   audio stays within the same bound as WebSocket and synthesis pauses instead of growing memory.

---

### User Story 3 - Run both transports and select them by configuration (Priority: P2)

An operator starts the service with WebSocket, gRPC, or both enabled, using configuration only.
Both transports share one engine, one admission policy (the concurrency limit applies across both),
and one health/readiness status. gRPC binds to localhost by default like WebSocket.

**Why this priority**: Comparing transports with the same engine and model under the same
conditions requires running either one without changing engine or core behavior.

**Independent Test**: Start the service with only gRPC, only WebSocket, and both; confirm each
enabled transport serves a request, a disabled one refuses connections, and readiness reflects the
shared engine state.

**Acceptance Scenarios**:

1. **Given** only gRPC is enabled, **When** a WebSocket client connects, **Then** the connection is
   refused and gRPC requests succeed.
2. **Given** both transports are enabled, **When** a WebSocket request is active and the
   concurrency limit is 1, **Then** a gRPC request is rejected with "busy".
3. **Given** default configuration, **When** the service starts, **Then** both WebSocket and gRPC
   are enabled and each endpoint listens on localhost only.

---

### User Story 4 - Documented gRPC client and contract (Priority: P3)

A developer finds the gRPC request/response contract documented next to the WebSocket one, plus a
runnable gRPC example client in Spanish mirroring the existing WebSocket example (simulated LLM
streaming, voice choice, cancellation, unsupported voice).

**Why this priority**: The constitution requires examples and documented contracts for both
transports, but they add no runtime value on their own.

**Independent Test**: Follow only the README instructions to run each gRPC example against a
running service and observe the documented outputs.

**Acceptance Scenarios**:

1. **Given** a fresh clone with models installed, **When** a developer follows the README, **Then**
   they can run the gRPC example client and hear/save Spanish audio.
2. **Given** the contract document, **When** compared with the WebSocket protocol document,
   **Then** every message, field and error code maps one to one between the two.

---

### Edge Cases

- A client sends text pieces after end-of-text, or end-of-text twice.
- A client opens a second gRPC call while its first is still active: it is subject to the
  service-wide concurrency limit and is rejected with "busy" when the limit is reached.
- A client sends a second open-request message within the same gRPC call: it is rejected with a
  structured error and the first request is unaffected.
- The client cancels at the same moment the last audio chunk is produced.
- Text exceeds the per-request character limit part-way through the stream.
- The client never sends text or end-of-text (idle timeout).
- A message exceeds the maximum message size the transport allows (large text piece).
- The engine fails to load or fails mid-stream while the other transport is serving a request.
- The gRPC port is already in use at startup.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The service MUST provide a gRPC transport that lets a client open a synthesis
  request, stream Spanish text pieces to the service, and receive streamed audio on one call.
- **FR-002**: The gRPC transport MUST expose application-level functionality equivalent to the
  WebSocket transport: request open with optional voice, text pieces, end-of-text, cancel,
  acknowledgement, audio chunks, completion, cancellation confirmation, and errors.
- **FR-003**: Audio chunks MUST carry request identifier, sequence number, a last-chunk indicator,
  and audio metadata (encoding, sample rate, channels), using the same audio format as WebSocket
  (16-bit PCM, 24 kHz, mono). Audio chunks MUST be distinguishable from control messages.
- **FR-004**: Streaming semantics MUST match WebSocket: audio starts from the text received so far
  without waiting for the rest; chunks are in order and continuous; an explicit terminal event
  (completed, cancelled, or error) ends every stream.
- **FR-005**: Cancellation MUST stop audio delivery and inference within the same bound as
  WebSocket and MUST release request resources. Clients MUST be able to cancel with an explicit
  cancel message, which receives a "cancelled" confirmation; cancelling or dropping the call, like
  a client disconnect, MUST also stop the request and release resources, without a confirmation.
- **FR-006**: Error conditions MUST use the same error codes, meanings and structured fields as
  the WebSocket transport, and MUST NOT expose internal details.
- **FR-007**: The gRPC transport MUST reuse the existing engine interface, session logic,
  segmentation, admission control, limits (text length, timeouts, concurrency) and voice
  verification gate; it MUST NOT contain engine-specific logic, and engine/core logic MUST NOT
  contain transport-specific logic.
- **FR-008**: The concurrency limit MUST apply service-wide across both transports; requests
  beyond it MUST be rejected with a structured "busy" error. Each gRPC call
  carries exactly one request (a client opens a new call for each request, and cancelling or
  dropping the call cancels that request); a second request on a WebSocket connection keeps its
  existing "busy" behavior.
- **FR-009**: Buffered, undelivered audio and pending text MUST be bounded per request exactly as
  for WebSocket, and a slow client MUST cause backpressure rather than unbounded memory growth.
- **FR-010**: Operators MUST be able to enable WebSocket, gRPC, or both through configuration
  without changing engine or core behavior; both MUST be enabled by default, and the gRPC port MUST
  be configurable.
- **FR-011**: The gRPC endpoint MUST bind to localhost by default; non-local binding MUST require
  the same explicit opt-in as WebSocket.
- **FR-012**: Health and readiness MUST reflect the shared engine state and MUST be served by the
  existing HTTP health/readiness endpoints whenever any transport is enabled, including a
  gRPC-only deployment. No separate gRPC health check is required.
- **FR-013**: Every gRPC request MUST carry a correlation identifier in logs; logs MUST NOT contain
  full user text or audio by default. Logs and metrics MUST allow transport delivery time to be
  distinguished from model generation time, per transport.
- **FR-014**: All audio MUST remain Spanish; the same Spanish-only rules, default voice and
  rejection of non-Spanish voices apply on gRPC.
- **FR-015**: A single set of contract tests MUST run against both transports with the same
  expectations, and a transport MUST pass them before being considered supported.
- **FR-016**: The repository MUST document the gRPC contract alongside the WebSocket contract and
  provide Spanish gRPC example clients mirroring the WebSocket examples; the README MUST
  distinguish tested gRPC capabilities from planned ones.

### Key Entities

- **Synthesis request**: One stream of text in and audio out, identified by a request identifier;
  has a voice, a lifecycle (open, streaming, completed, cancelled, failed) and limits.
- **Text piece**: A small fragment of Spanish text sent by the client, plus the end-of-text signal.
- **Audio chunk**: An ordered fragment of audio with request identifier, sequence number,
  last-chunk indicator and format metadata.
- **Control event**: Acknowledgement, completion, cancellation confirmation, or structured error.
- **Transport**: A way of carrying requests (WebSocket or gRPC) over the same shared service core.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: 100% of the shared contract tests (streaming flow, cancellation, errors, text limit,
  capabilities) pass against gRPC with the same expectations used for WebSocket.
- **SC-002**: For the same Spanish text, voice and engine, the audio received over gRPC and over
  WebSocket is identical in format and content in 100% of tested runs.
- **SC-003**: In a streamed-text test, the first audio chunk arrives before the client has sent
  the final text piece in 100% of runs over gRPC.
- **SC-004**: After a cancel or abrupt disconnect over gRPC, audio stops and resources are
  released within the same time bound measured for WebSocket, in 100% of tested runs.
- **SC-005**: With both transports enabled and a concurrency limit of 1, a second simultaneous
  request on either transport is rejected with "busy" in 100% of tested runs.
- **SC-006**: Peak process memory over 20 consecutive gRPC requests stays within the same ceiling
  as WebSocket (under 4 GB) with no out-of-memory failure.
- **SC-007**: A developer can start the service and hear Spanish audio from the gRPC example in
  under 5 minutes by following only the README.
- **SC-008**: Every WebSocket message, field and error code has a documented gRPC counterpart,
  with no unmapped items.

## Assumptions

- Out of scope for this feature: the benchmarking harness and measurement reports (the next
  feature), the VibeVoice engine, authentication and encryption, remote (non-localhost)
  deployment, and any audio playback UI. This feature only makes the transport benchmarkable.
- Transport framing differences (for example, how messages are delimited) are allowed as long as
  application-level meaning, ordering, and limits are equivalent.
- The audio format stays fixed at 16-bit PCM, 24 kHz, mono; compressed formats are out of scope.
- The gRPC transport runs in the same process as the WebSocket transport, sharing one loaded
  model, and both can be enabled together; separate processes are not required.
- The gRPC default port is a new, distinct local port from the WebSocket port; the exact value is
  a planning decision.
- Text is plain Spanish, streamed in small pieces as a language model would emit it; markup and
  SSML remain out of scope.
- The existing mock engine and deterministic fixtures are reused so contract tests do not need to
  download large models.
- Target environment is unchanged: macOS on Apple Silicon (M2 Pro, 16 GB), CPU baseline.
