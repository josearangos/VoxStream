# Feature Specification: Gradio Teleprompter Demo

**Feature Branch**: `003-gradio-teleprompter-demo`

**Created**: 2026-10-10

**Status**: Draft

**Input**: User description: "Create a demo using Gradio to interact with the API in WebSocket. The idea is to enter text and have the audio play in realtime, just a text input, and then simulate what is being played as if it were a teleprompter."

## Clarifications

### Session 2026-10-10

- Q: How finely should the teleprompter mark progress through the text? → A: Word level: a moving highlight across words, with position estimated from audio played within each segment.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Type text and hear it spoken in real time (Priority: P1)

A person opens the demo page in their browser, types or pastes Spanish text into a single text
box, and presses a button. The demo sends the text to the running VoxStream service over its
WebSocket interface and starts playing the returned speech as soon as the first audio arrives,
without waiting for the full text to be synthesized.

**Why this priority**: Hearing audio start quickly from plain text is the core of the demo and
shows VoxStream's real-time streaming value. It is a viable MVP on its own.

**Independent Test**: With the service running, enter a multi-sentence Spanish paragraph, press
the button, and verify that audible speech begins within a couple of seconds and continues
smoothly to the end of the text.

**Acceptance Scenarios**:

1. **Given** the service is running and the page is open, **When** the user enters text and
   starts playback, **Then** speech begins before the whole text has finished synthesizing.
2. **Given** playback is in progress, **When** the audio finishes, **Then** the demo shows that
   the stream is complete and the user can submit new text.
3. **Given** the text box is empty or only whitespace, **When** the user tries to start,
   **Then** nothing is sent and a clear message asks for text.

---

### User Story 2 - Follow the spoken text like a teleprompter (Priority: P1)

While the audio plays, the page displays the submitted text as a teleprompter: the words
already spoken are visually distinguished from the words still to come, a highlight moves word by
word in step with what the user is hearing, and the view keeps the current position in sight
for long texts.

**Why this priority**: The teleprompter simulation is the second half of the requested demo and
is what makes the real-time behavior visible, not just audible.

**Independent Test**: Start playback of a long paragraph and verify that the highlighted
position moves forward in rough sync with the audio (within about one second), stays visible
without manual scrolling, and ends at the end of the text when audio ends.

**Acceptance Scenarios**:

1. **Given** playback has started, **When** audio is heard, **Then** the words up to the
   currently spoken word are marked as spoken, the current word is highlighted, and the remainder
   is marked as upcoming.
2. **Given** a text longer than the visible area, **When** playback advances, **Then** the view
   scrolls automatically so the current position remains visible.
3. **Given** playback ends normally, **When** the final audio is played, **Then** the entire text
   is marked as spoken.

---

### User Story 3 - Stop playback and recover from problems (Priority: P2)

The user can stop playback at any time, which halts audio and the teleprompter and cancels the
request on the service. If the service is unreachable or reports an error, the demo shows a
plain-language message instead of failing silently, and the user can try again.

**Why this priority**: A demo that hangs or stays silent on failure is confusing, but this is
secondary to the main flow.

**Independent Test**: Start playback, press stop, and verify audio ceases quickly and the page
returns to a ready state; then stop the service, press start, and verify an understandable error
is shown.

**Acceptance Scenarios**:

1. **Given** playback is in progress, **When** the user presses stop, **Then** audio and
   teleprompter stop within about one second and the page is ready for new text.
2. **Given** the service is not running, **When** the user starts playback, **Then** a message
   explains the service could not be reached and no stuck state remains.
3. **Given** the service returns an error mid-stream, **When** it occurs, **Then** the error is
   shown, playback ends cleanly, and the user can start again.

---

### Edge Cases

- Text exceeding the service's maximum length: the demo informs the user of the limit instead of
  sending a request that will be rejected.
- Service busy with another request: the demo shows a "busy, try again" message.
- User starts a new playback while one is active: the active one is stopped first (or start is
  disabled until it ends); two simultaneous streams never play overlapped.
- Text containing line breaks, numbers, or punctuation only: handled without breaking the
  teleprompter display.
- Browser blocks automatic audio: the demo tells the user how to allow playback.
- Connection drops mid-stream: shown as an error; partially played text remains marked as spoken.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The demo MUST present a single text input and a control to start playback.
- **FR-002**: The demo MUST send the entered text to the VoxStream service over its WebSocket
  interface and play the returned audio incrementally as it arrives.
- **FR-003**: The demo MUST begin audible playback without waiting for the complete audio.
- **FR-004**: The demo MUST display the submitted text as a teleprompter, distinguishing spoken
  words from upcoming words and advancing a word-level highlight in step with the audio actually played.
- **FR-005**: The teleprompter MUST keep the current position visible for texts longer than the
  visible area.
- **FR-006**: The demo MUST provide a stop control that halts audio and teleprompter and cancels
  the request on the service.
- **FR-007**: The demo MUST reject empty input with a clear message and send nothing.
- **FR-008**: The demo MUST show understandable messages for an unreachable service, a busy
  service, over-length text, and service-reported errors, and MUST return to a ready state after
  each.
- **FR-009**: The demo MUST indicate the current state (ready, connecting, playing, finished,
  stopped, error) at all times.
- **FR-010**: The demo MUST allow the service address to be configured without code changes, with
  a sensible local default.
- **FR-011**: The demo MUST NOT require authentication, accounts, or persistent storage; entered
  text is not retained after the session.
- **FR-012**: The demo MUST be a client of the existing service interface only and MUST NOT
  require changes to the service or its protocol.

### Key Entities

- **Playback Session**: One run from pressing start to completion, stop, or error; has a state,
  the submitted text, and the position reached.
- **Teleprompter Position**: How much of the submitted text is considered spoken at a given
  moment, derived from the audio played so far.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: A first-time user can go from opening the page to hearing speech in under 1 minute
  with no instructions beyond the page itself.
- **SC-002**: Audible speech begins within 2 seconds of pressing start for a typical paragraph
  when the service is running locally.
- **SC-003**: The highlighted word stays within 1 second of what is being heard throughout
  playback of a 1-minute text.
- **SC-004**: Stopping playback silences audio within 1 second in 95% of attempts.
- **SC-005**: In every tested failure case (service down, busy, over-length text, mid-stream
  error), the user sees an explanatory message and can start again without reloading the page.

## Assumptions

- The VoxStream WebSocket service from feature 001 is running locally and reachable; the demo
  does not start it.
- Input text is Spanish, consistent with the project's Spanish-only audio rule.
- The service does not report word-level timing, so teleprompter position is estimated from the
  amount of audio played relative to the text, at word granularity (estimated, not exact).
- Single local user; no concurrency, authentication, or deployment concerns for this demo.
- The demo is a showcase tool, not a production interface; mobile layout and voice selection are
  out of scope.
