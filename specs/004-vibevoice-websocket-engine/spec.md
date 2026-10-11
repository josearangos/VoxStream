# Feature Specification: Microsoft VibeVoice Spanish Engine (WebSocket)

**Feature Branch**: `004-vibevoice-websocket-engine`

**Created**: 2026-10-10

**Status**: Draft

**Input**: User description: "Let's start new feature to add new engine Microsoft VibeVoice in spanish too, only websocket"

## Clarifications

### Session 2026-10-10

- Q: If no VibeVoice voice passes Spanish verification, should the engine still ship? → A: The engine is built but refuses to synthesize (structured error) unless at least one voice is verified as Spanish; the failed result is documented.
- Q: What is the acceptable time to first audio chunk for a one-sentence Spanish request on the reference MacBook Pro? → A: Within 2 seconds; a miss is still recorded in the measurements.
- Q: Which voices does the VibeVoice engine offer? → A: Only the preset voices shipped with the model; user-supplied or cloned voices are out of scope.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Stream Spanish speech from VibeVoice over WebSocket (Priority: P1)

An operator starts the VoxStream service selecting the VibeVoice engine instead of Kokoro. A client
connects over WebSocket exactly as it does today, sends Spanish text (in pieces, as a language model
would), and receives ordered Spanish audio chunks followed by a completion message. The client does
not need to change anything except, optionally, the voice name.

**Why this priority**: This delivers the whole value of the feature: a second, interchangeable
Spanish engine reachable through the existing WebSocket protocol. It is a viable MVP on its own.

**Independent Test**: Start the service with the VibeVoice engine, send a Spanish paragraph over
WebSocket, and verify that audio arrives incrementally, in order, is playable Spanish speech, and the
stream ends with an explicit completion message.

**Acceptance Scenarios**:

1. **Given** the service is configured with the VibeVoice engine, **When** a client opens a valid
   request and sends Spanish text, **Then** it receives an acknowledgement stating the engine, voice,
   and audio format, followed by audio chunks and a completion message.
2. **Given** a request that omits the voice, **When** it is processed, **Then** the default Spanish
   VibeVoice voice is used and the response states which voice was used.
3. **Given** a request naming a voice that the VibeVoice engine does not offer, **When** it is
   processed, **Then** the client receives a structured error and no audio.
4. **Given** the same Spanish text, **When** sent once with Kokoro and once with VibeVoice, **Then**
   both streams use the same message protocol and differ only in the engine/voice reported.

---

### User Story 2 - Verify the VibeVoice voices speak Spanish (Priority: P2)

A maintainer runs the existing Spanish verification for the VibeVoice engine and learns whether each
offered voice produces intelligible Spanish. A voice that fails is not offered as a Spanish voice.

**Why this priority**: The project requires all audio to be Spanish; the engine must not be usable
without proof of that.

**Independent Test**: Run the verification for VibeVoice and confirm it reports pass/fail per voice
against the same reference sentences and threshold used for Kokoro.

**Acceptance Scenarios**:

1. **Given** the VibeVoice engine is installed, **When** verification runs, **Then** each voice gets
   a pass/fail result using the same criteria as the existing engine.
2. **Given** a voice fails verification, **When** the service lists available voices, **Then** that
   voice is excluded or clearly flagged as not verified for Spanish.

---

### User Story 3 - Compare VibeVoice against Kokoro with measurements (Priority: P3)

A maintainer runs the existing latency and cancellation measurements against VibeVoice and records
time to first audio, inter-chunk delay, real-time factor, and memory use next to the Kokoro results.

**Why this priority**: Fair, reproducible engine comparison is a stated project goal, but it builds
on the engine already streaming.

**Independent Test**: Run the measurement suite for both engines on the same machine and confirm the
results document contains comparable rows for each.

**Acceptance Scenarios**:

1. **Given** both engines are available, **When** the measurement suite runs, **Then** results for
   each engine are recorded with the same metrics and test inputs.
2. **Given** a client cancels an in-progress VibeVoice stream, **When** cancellation is received,
   **Then** audio generation stops and the measured stop time is recorded.

---

### Edge Cases

- VibeVoice model files or dependencies are missing: the service fails at startup (or on first
  request) with a clear, structured error naming what is missing; Kokoro and mock remain usable.
- The machine lacks enough memory for the model: a clear error is reported rather than a crash or
  unbounded memory growth.
- No voice passes Spanish verification: the engine refuses requests with a structured error
  stating that no Spanish-verified voice is available.
- The client cancels mid-stream or disconnects abruptly: generation stops and resources are released.
- Text containing numbers, accents, or punctuation typical of Spanish (¿ ¡ ñ) is synthesized correctly.
- Empty or whitespace-only text, or text above the configured length limit, is rejected with the same
  structured errors as for Kokoro.
- A second request on a busy connection or above the concurrency limit is rejected with the existing
  "busy" error.
- gRPC is not part of this feature: selecting VibeVoice while using the gRPC transport reports a
  clear "engine not supported on this transport" error rather than failing obscurely.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The system MUST offer VibeVoice as a selectable engine alongside the existing engines,
  chosen by configuration without changes to transport logic.
- **FR-002**: The VibeVoice engine MUST synthesize Spanish speech and stream it incrementally, not
  only after the whole text is synthesized.
- **FR-003**: The VibeVoice engine MUST be reachable over the existing WebSocket protocol with no
  protocol changes visible to clients.
- **FR-004**: The system MUST NOT expose VibeVoice over gRPC in this feature, and MUST report a
  clear error if that combination is requested.
- **FR-005**: The system MUST provide a default Spanish VibeVoice voice and allow selecting other
  verified preset voices by name; unknown voices MUST yield a structured error.
- **FR-006**: The system MUST document the engine's supported languages, voices, audio format,
  runtime requirements, memory consumption, and streaming capabilities.
- **FR-007**: The system MUST verify each VibeVoice voice produces intelligible Spanish using the
  same criteria as the existing engine, and MUST NOT present unverified voices as Spanish voices.
- **FR-007a**: If no VibeVoice voice passes Spanish verification, the engine MUST refuse to
  synthesize with a structured error, and the failed verification result MUST be documented.
- **FR-008**: Cancellation MUST propagate to VibeVoice generation, and generation MUST stop
  promptly after a cancel or disconnect.
- **FR-009**: Audio buffering for VibeVoice MUST be bounded, like other engines.
- **FR-010**: Engine-specific dependencies MUST be optional and isolated so the service runs with
  Kokoro or mock without installing VibeVoice requirements.
- **FR-011**: Missing model files, missing dependencies, or insufficient resources MUST produce
  clear structured errors.
- **FR-012**: The system MUST report the engine, voice, sample rate, and encoding of the audio in
  the stream acknowledgement.
- **FR-013**: Measurements for VibeVoice (time to first audio, inter-chunk delay, real-time factor,
  memory, cancel latency) MUST be recorded in the project measurements document alongside Kokoro.

### Key Entities

- **VibeVoice Engine**: An interchangeable speech-synthesis engine with a name, supported language
  (Spanish), list of voices, audio format, and streaming/cancellation capabilities.
- **Voice**: A named speaker offered by an engine, with a Spanish verification status.
- **Verification Result**: Per-voice pass/fail outcome against reference Spanish sentences.
- **Measurement Record**: Per-engine latency, throughput, and memory results for a given machine.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Switching from Kokoro to VibeVoice requires changing only the engine setting; an
  existing WebSocket client works unmodified for 100% of the existing protocol scenarios.
- **SC-002**: Every voice offered as Spanish has passed the Spanish intelligibility verification, and at least one passes or the engine refuses to synthesize (FR-007a).
- **SC-003**: For a one-sentence Spanish request on the reference MacBook Pro with the model
  already loaded (warm start), the first audio chunk arrives within 2 seconds, and a listener hears
  audio begin before the full text has finished synthesizing. Cold-start time is reported
  separately. A miss is still recorded in the measurements.
- **SC-004**: After a cancel, audio stops arriving within 500 ms (the bound used for Kokoro), or the
  measured difference is explained in the measurements document.
- **SC-005**: A maintainer can reproduce engine comparison results for both engines from a single
  documented procedure.
- **SC-006**: The service starts and passes its existing test suite with VibeVoice dependencies
  not installed.

## Assumptions

- VibeVoice (Microsoft's open-source speech model) can run locally on the reference Apple Silicon
  machine (16 GB, no discrete GPU) at a size that fits memory; if only a smaller or quantized variant
  fits, that variant is used and documented.
- Spanish support may be limited or experimental in the chosen VibeVoice variant; the verification
  in User Story 2 is the gate for what is advertised as Spanish.
- The existing WebSocket protocol, bounded buffers, cancellation, error model, and Spanish
  verification tooling are reused as-is.
- Model files are obtained by the operator (downloaded separately) and are not committed to the repo.
- Only preset voices shipped with the model are offered; user-supplied voices are out of scope.
- Voice cloning, multi-speaker long-form generation, and non-Spanish output are out of scope.
- gRPC support for VibeVoice is out of scope and may be a later feature.
