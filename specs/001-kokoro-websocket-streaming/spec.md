# Feature Specification: Kokoro Spanish TTS Streaming over WebSocket

**Feature Branch**: `001-kokoro-websocket-streaming`

**Created**: 2026-10-10

**Status**: Draft

**Input**: User description: "Stream Spanish text-to-speech audio from the Kokoro-ONNX engine over WebSocket. Include a common engine interface, bounded buffers, cancellation, structured errors, and verification that the selected Kokoro model and voices produce Spanish speech."

## Clarifications

### Session 2026-10-10

- Q: How should the service decide that a Kokoro voice produces intelligible Spanish speech? → A: Automated check that transcribes the generated audio with a Spanish speech-recognition model and requires the text to match the reference sentence within an error threshold, plus a one-time manual listen for sign-off.
- Q: What should happen when a client sends a new synthesis request on a connection that is already streaming audio? → A: Reject it with a structured "busy" error; the first stream continues unaffected. One active request per connection.
- Q: How should audio be sent to the client over the WebSocket? → A: Audio chunks as binary frames with a small header carrying the request identifier and sequence number; control messages as JSON text frames.
- Q: What is the default maximum number of requests handled at the same time? → A: 1 (strictly sequential), configurable; requests beyond the limit are rejected with a structured "busy" error.
- Q: What should the default maximum text length per request be? → A: 2,000 characters in total per request (configurable). The text is NOT sent in one piece: it arrives as a stream of text pieces, simulating an LLM streaming tokens to the service in the last stage of a voice agent, and the service must start producing audio from the text received so far without waiting for the rest.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Stream Spanish speech while text is still arriving (Priority: P1)

A client (for example, the language-model stage of a voice agent) connects to the local VoxStream
service over WebSocket, opens a request, and sends Spanish text in small pieces as it is produced.
The service does not wait for the full text: as soon as enough text has arrived to form a speakable
segment (such as a sentence or phrase), it synthesizes it and streams the audio back, while later
text is still arriving. When the client signals the end of the text, the service finishes the
remaining audio and sends an explicit completion message. Each audio chunk carries enough metadata
(request identifier, sequence number, encoding, sample rate, channels) for the client to decode and
play it correctly.

**Why this priority**: This is the core value of VoxStream: hearing Spanish audio quickly. Without
it nothing else matters, and it alone is a viable MVP.

**Independent Test**: Connect a client that sends a Spanish paragraph in small pieces with short
pauses between them (simulating a streaming language model), and verify that the first audio chunk
arrives before the last piece of text has been sent, chunks arrive in order, the concatenated audio
is playable, and a completion message ends the stream after the end-of-text signal.

**Acceptance Scenarios**:

1. **Given** the service is ready, **When** a client opens a valid request, **Then** it receives an
   acknowledgement with a request identifier and the audio format, and can then send text pieces.
2. **Given** a request is open, **When** text pieces arrive that complete a first sentence, **Then**
   audio for that sentence starts streaming back before the remaining text has been received.
3. **Given** the client has sent the end-of-text signal, **When** all remaining audio has been
   delivered, **Then** the client receives ordered audio chunks followed by a completion message.
4. **Given** a client that sends its entire text in a single piece followed by end-of-text,
   **When** it is processed, **Then** it still streams audio incrementally by segment and completes
   normally.
5. **Given** a request that omits voice configuration, **When** it is processed, **Then** the
   default Spanish voice is used and the response states which voice was used.
6. **Given** a completed stream, **When** the client reassembles all chunks in order, **Then** the
   result is continuous, playable audio with no gaps or reordering.

---

### User Story 2 - Cancel an in-progress stream (Priority: P2)

A client that no longer needs the audio (for example, the user skipped ahead) cancels the request
or disconnects. The service stops producing audio for that request promptly and releases its
resources.

**Why this priority**: Prevents wasted compute and memory on a 16 GB machine and keeps the service
responsive for the next request.

**Independent Test**: Start a request, stream text pieces, send a cancel message after the first
audio chunk, and verify that no further audio chunks arrive, further text pieces are ignored, a
cancelled status is reported, and the service is immediately able to accept a new request. Repeat by dropping the connection and verify no
generation continues.

**Acceptance Scenarios**:

1. **Given** a stream in progress, **When** the client sends a cancel for that request, **Then**
   audio delivery stops and the client receives a cancelled confirmation.
2. **Given** a stream in progress, **When** the client disconnects abruptly, **Then** generation
   for that request stops and its resources are released.
3. **Given** a cancelled request, **When** a new request is submitted, **Then** it is served
   normally without residual effects from the cancelled one.

---

### User Story 3 - Receive clear, structured errors (Priority: P2)

When a request is malformed, too large, uses an unsupported language or voice, or the engine fails,
the client receives a structured error message identifying the request, an error category, and an
actionable explanation, without internal details leaking.

**Why this priority**: Clients need to distinguish failure from completion and recover correctly;
the constitution requires explicit error signalling.

**Independent Test**: Send each class of invalid request (malformed message, empty text, text over
the limit, text piece with no open request, non-Spanish language or voice, unknown engine) and verify each yields a distinct
structured error and the connection remains usable where appropriate.

**Acceptance Scenarios**:

1. **Given** a malformed message, **When** it is received, **Then** the client gets a structured
   error with a stable error code and a human-readable message.
2. **Given** the total text received for a request exceeds the configured limit (default 2,000
   characters), **When** the piece that crosses the limit arrives, **Then** the request ends as
   failed with a structured "text too long" error; audio already delivered stays valid, and the
   service stops accepting further text for it.
3. **Given** a request for a non-Spanish language or a voice that is not a verified Spanish
   voice, **When** submitted, **Then** it is rejected with an error explaining which Spanish
   voices are available; no fallback voice is used silently.
4. **Given** the engine fails mid-stream, **When** the failure occurs, **Then** the client
   receives an error message that clearly ends the stream as failed, distinct from completion.
5. **Given** the service has reached its concurrent-request limit, **When** another request
   arrives, **Then** it is rejected with a structured "busy" error.
6. **Given** a client sends a text piece with no open request, after end-of-text, or after
   cancellation, **When** it is received, **Then** the client gets a structured error and the
   connection remains usable.

---

### User Story 4 - Verify the model and voices produce Spanish (Priority: P1)

An operator runs a verification that confirms the selected Kokoro model and each exposed voice
actually produce intelligible Spanish speech. Only voices that pass are offered to clients.

**Why this priority**: The constitution requires all audio to be Spanish. Support for Spanish in
the chosen model and voices must be demonstrated, not assumed, and it determines which voices the
service may expose.

**Independent Test**: Run the verification against a fixed set of Spanish reference sentences and
check that it reports pass or fail per voice, with a stored result that lists the model version
and voices checked.

**Acceptance Scenarios**:

1. **Given** the installed model and candidate voices, **When** verification runs, **Then** each
   voice's generated audio is transcribed and compared with its reference sentence, and receives a
   pass (word error rate within the configured threshold) or fail result, recorded with the model
   version; the manual listening sign-off date is recorded separately and a missing sign-off is a
   warning, not a failure.
2. **Given** a voice that fails verification, **When** the service starts, **Then** that voice is
   not exposed and requests for it are rejected as unsupported.
3. **Given** no voice passes verification, **When** the service starts, **Then** it reports not
   ready with an actionable explanation instead of producing non-Spanish audio.

---

### User Story 5 - Swap engines through a common interface (Priority: P3)

A developer can add or select a different speech engine without changing how clients connect or
how the streaming protocol works. The service describes what the active engine can do (voices,
languages, audio format, and whether it generates audio incrementally or only delivers chunks of
already-completed audio).

**Why this priority**: Enables the planned VibeVoice engine and gRPC transport later; lower
priority now because only one engine is delivered in this feature.

**Independent Test**: Run the full streaming, cancellation, and error test suite against a
deterministic mock engine and against the Kokoro engine, using the same tests, and verify the same
results.

**Acceptance Scenarios**:

1. **Given** the mock engine is selected through configuration, **When** a client streams text,
   **Then** the protocol behaves identically to the Kokoro engine.
2. **Given** a client asks for engine capabilities, **When** the request is processed, **Then** the
   response states supported languages, voices, audio format, and the streaming mode (true
   incremental, chunked from text segments, or complete-text then chunked delivery).

---

### Edge Cases

- Empty or whitespace-only text pieces; text containing only punctuation or digits.
- Text pieces that split a word, a number, or a sentence in the middle.
- Sentence-like punctuation that is not a sentence end (abbreviations such as "Sr.", decimals,
  ellipses).
- Text arriving faster than it can be synthesized (pending text must stay bounded).
- Text arriving slowly, or the client never sending end-of-text (idle timeout).
- End-of-text arriving with unspoken leftover text that has no sentence ending.
- Total text exceeding the configured limit; total text at exactly the limit.
- Spanish text with accents, ñ, inverted punctuation, numbers, abbreviations, and mixed-in English
  words.
- Text in a language other than Spanish.
- Client sends a second request on the same connection while one is still streaming (rejected as busy; the active stream is unaffected).
- Client is slow to consume audio, so buffered audio would otherwise grow without limit.
- Client disconnects during synthesis, during delivery, or immediately after connecting.
- Cancellation arrives after the last chunk was produced but before completion was sent.
- Model files are missing, corrupted, or fail to load at startup.
- The machine runs low on memory during synthesis.
- Request exceeds the configured timeout.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The service MUST allow a client to open a synthesis request over WebSocket with
  optional engine and voice settings, then send the text as a sequence of text pieces, then signal
  end-of-text.
- **FR-002**: The service MUST assign each request an identifier, return it to the client, and
  include it on every message related to that request.
- **FR-003**: The service MUST deliver audio incrementally in ordered chunks, each carrying a
  sequence number, so that playback can begin before the full text has been received or
  synthesized.
- **FR-004**: The service MUST describe the audio format (encoding, sample rate, channels) to the
  client before or with the first chunk, sufficient to decode and play every chunk.
- **FR-005**: Audio chunks MUST be sent as binary frames, each with a small header carrying the
  request identifier and sequence number, and control messages (acknowledgement, completion,
  cancellation, error) MUST be sent as JSON text frames, so the two are always distinguishable.
- **FR-006**: The service MUST send an explicit completion message when all audio has been
  delivered, and clients MUST be able to tell completed, cancelled, and failed streams apart.
- **FR-007**: The service MUST allow a client to cancel an in-progress request and MUST stop audio
  generation and delivery for it as soon as the engine supports doing so.
- **FR-008**: The service MUST stop generation and release resources when a client disconnects,
  leaving no orphaned generation tasks.
- **FR-009**: The service MUST limit the amount of buffered, undelivered audio per request to a
  configurable bound and MUST apply backpressure so a slow client cannot cause unbounded memory
  growth.
- **FR-010**: The service MUST validate every request (message structure, text presence and
  length, voice, language, engine) and reject invalid requests and text pieces as early as
  possible.
- **FR-011**: Errors MUST be returned as structured messages containing the request identifier
  (when known), a stable error code, a category, and an actionable message, and MUST NOT expose
  internal paths, stack traces, or other sensitive details.
- **FR-012**: The service MUST define a common engine interface covering initialization,
  synthesis, cancellation, shutdown, and capability reporting, and the transport MUST rely only on
  that interface.
- **FR-013**: The active engine MUST be selectable through configuration without changing
  transport behavior. A request naming an engine other than the configured, loaded engine MUST be
  rejected with `UNSUPPORTED_ENGINE`.
- **FR-014**: The Kokoro engine MUST be provided as the first implementation of the engine
  interface, and a deterministic mock engine MUST exist for tests.
- **FR-015**: The service MUST report each engine's capabilities, including supported languages,
  available voices, audio format, and whether synthesis is truly incremental, chunked from text
  segments, or complete-text followed by chunked delivery.
- **FR-016**: All audio MUST be Spanish. Requests for another language, or for a voice that has
  not passed Spanish verification, MUST be rejected with a structured error and MUST NOT fall back
  silently.
- **FR-017**: The default voice and language MUST be Spanish.
- **FR-018**: The system MUST provide a verification procedure that checks the selected Kokoro
  model and each candidate voice against a fixed set of Spanish reference sentences by
  transcribing the generated audio with a Spanish speech-recognition model and requiring a word
  error rate within a configurable threshold. The automated result MUST be recorded with the model
  version and MUST gate which voices the service exposes. A one-time manual listening sign-off
  MUST also be recorded; a missing sign-off MUST be reported as a warning but MUST NOT hide the
  voice. The recognition model is needed only for verification, not for serving requests.
- **FR-019**: If no voice passes Spanish verification, or the model cannot be loaded, the service
  MUST report itself as not ready with an actionable reason.
- **FR-020**: The service MUST enforce configurable limits for total text length per request
  (default 2,000 characters), request duration, and concurrent requests. The default concurrency limit is 1 active request service-wide; requests
  beyond the limit MUST be rejected with a structured "busy" error.
- **FR-021**: The service MUST expose health and readiness status for local operation, including
  which execution provider the engine is actually using.
- **FR-022**: The service MUST bind to localhost by default and MUST NOT send text or audio to any
  external service during synthesis.
- **FR-023**: Each request MUST carry a correlation identifier in logs; logs MUST NOT contain the
  full input text or audio by default.
- **FR-024**: The service MUST record timing for model generation separately from audio delivery
  (including time to first audio chunk) so that later benchmarking can distinguish them.
- **FR-025**: The service MUST load the Kokoro model lazily or on explicit configuration, and
  release request resources deterministically when a request ends for any reason.
- **FR-026**: Each connection MUST have at most one active request. A new request on a connection
  that is already streaming MUST be rejected with a structured "busy" error and MUST NOT affect
  the active stream.
- **FR-027**: The service MUST NOT require the full text before starting synthesis. It MUST
  accumulate incoming text pieces, split them into speakable segments (at sentence or phrase
  boundaries), and begin synthesizing each segment as soon as it is complete.
- **FR-028**: At end-of-text the service MUST synthesize any remaining unspoken text, even without
  a sentence ending, and then send the completion message.
- **FR-029**: The audio for consecutive segments MUST be delivered in text order with continuous
  sequence numbers across the whole request, so the client hears one continuous stream.
- **FR-030**: Text received but not yet synthesized MUST be held in a bounded buffer. If it
  fills, the service MUST apply backpressure to the client or fail the request with a structured
  error; it MUST NOT grow without limit.
- **FR-031**: If no text piece or end-of-text arrives within a configurable idle timeout, the
  service MUST finish the request with a structured timeout error (after speaking any pending
  complete segments) and release its resources.

### Key Entities *(include if feature involves data)*

- **Synthesis Request**: A client's ask to speak a stream of text. Attributes: request identifier,
  requested engine, requested voice, language, limits applied, total text received so far,
  state (open, ending, completed, cancelled, failed).
- **Text Piece**: One fragment of the incoming text. Attributes: request identifier, order,
  content; plus an end-of-text signal that closes the input.
- **Text Segment**: A speakable unit (sentence or phrase) formed from received text pieces and
  sent to the engine for synthesis.
- **Audio Chunk**: One ordered piece of audio. Attributes: request identifier, sequence number,
  audio payload, whether it is the final chunk.
- **Stream Descriptor**: The audio format information for a request. Attributes: encoding, sample
  rate, channels, voice used, engine used, streaming mode.
- **Control Message**: A non-audio message. Types: acknowledgement, completion, cancellation,
  error.
- **Error**: Attributes: request identifier (if known), code, category, actionable message.
- **Engine Capabilities**: What an engine offers. Attributes: supported languages, verified
  voices, audio formats, streaming mode, execution provider in use, memory footprint notes.
- **Voice Verification Result**: Outcome of the Spanish check. Attributes: voice, model version,
  reference sentences used, word error rate, pass or fail, manual sign-off date.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: When a client streams a typical Spanish sentence (around 100 characters) piece by
  piece, the first audio chunk arrives in under 1 second after the piece that completes the first
  sentence, on the target Apple M2 Pro machine once the service is warm.
- **SC-002**: For a Spanish paragraph (around 300 characters) streamed piece by piece, audio is
  generated faster than it plays back (real-time factor below 1.0) on the target machine.
- **SC-003**: 100% of audio chunks in a stream arrive in sequence order, and reassembling them
  produces audio that plays without gaps in 100% of test runs.
- **SC-004**: After a cancel or disconnect, audio delivery stops within 500 ms and the service
  accepts a new request immediately in 100% of test runs.
- **SC-005**: With a deliberately slow client, memory used for buffered audio stays within the
  configured bound throughout the stream.
- **SC-006**: 100% of the defined invalid-request classes return a structured error with a stable
  code, and none expose internal details.
- **SC-007**: 100% of the voices offered to clients have a recorded passing Spanish verification
  for the installed model version, and no request produces non-Spanish audio.
- **SC-008**: The same streaming, cancellation, and error tests pass unchanged against both the
  Kokoro engine and the mock engine.
- **SC-009**: The service runs on the target machine without a dedicated GPU, and stays at or
  below 4 GB peak process memory with no out-of-memory failure during 20 consecutive requests.
- **SC-010**: In a streamed-text test, the first audio chunk is delivered before the client has
  sent the final text piece in 100% of test runs, and the audio for a request that arrives in
  pieces is identical in content to the audio for the same text sent in a single piece.

## Assumptions

- The default concurrency limit is 1 active request across the whole service, configurable; the
  admission policy is to reject requests beyond the limit with a structured "busy" error.
- Input is plain Spanish text delivered as a stream of text pieces, as a language model would emit
  it; markup and SSML are out of scope. The text pieces are small (words or a few words); the
  service does not need to receive a whole sentence per piece.
- The service forms segments at sentence-ending punctuation by default, with a configurable
  fallback so that a long run of text without punctuation is still spoken; exact segmentation
  rules are a planning decision.
- Audio is delivered as raw uncompressed audio chunks in one fixed format; compressed formats are
  out of scope for this feature.
- Kokoro is assumed to support Spanish voices, but this is verified by User Story 4 and not taken
  as given. If it does not, the feature cannot ship until a Spanish-capable model is selected.
- Kokoro may synthesize per text segment rather than token by token; the service will split text
  into sentences or phrases and report the streaming mode as chunked from text segments, not true
  incremental inference.
- Model files are downloaded once during setup; inference needs no network access afterward.
- Target environment is macOS on Apple Silicon (M2 Pro, 16 GB); CPU execution is the guaranteed
  baseline, with hardware acceleration used only when verified.
- Out of scope: gRPC transport, VibeVoice engine, benchmarking harness, authentication, remote
  (non-localhost) deployment, and audio playback UI.
