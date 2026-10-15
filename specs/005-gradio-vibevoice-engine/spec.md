# Feature Specification: VibeVoice Engine in the Gradio Demo

**Feature Branch**: `005-gradio-vibevoice-engine`

**Created**: 2026-10-10

**Status**: Draft

**Input**: User description: "add the vibevoice engine to the gradio demo"

## Clarifications

### Session 2026-10-10

- Q: When the presenter picks an engine the running service isn't using, should the demo switch it or only show a message? → A: Only show a message; no switching. The demo shows the engine the service runs, lets the presenter pick that engine's voices, and shows other engines as unavailable with a restart hint.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Hear the teleprompter demo with VibeVoice (Priority: P1)

A presenter has the VoxStream service running with the VibeVoice engine. They open the Gradio demo,
type Spanish text, and press play. The demo streams the speech from VibeVoice, plays it as it
arrives, and highlights the teleprompter in step with the audio, exactly as it does with Kokoro. The
demo shows which engine is speaking, so the audience knows what they are hearing.

**Why this priority**: This is the whole point of the feature: the demo must work end to end with
the second engine and make clear which engine is in use. It is a viable MVP on its own.

**Independent Test**: Start the service with VibeVoice, open the demo, play a Spanish paragraph, and
verify that audio starts before the full text is synthesized, the teleprompter follows, and the
active engine name is visible.

**Acceptance Scenarios**:

1. **Given** the service runs with VibeVoice, **When** the presenter plays a Spanish text, **Then**
   audio plays incrementally and the teleprompter advances with it.
2. **Given** the service runs with VibeVoice, **When** the demo page is open, **Then** it displays
   "VibeVoice" as the active engine before and during playback.
3. **Given** the service runs with Kokoro, **When** the demo plays a text, **Then** behavior is
   unchanged and the demo displays "Kokoro".

---

### User Story 2 - See engines and choose a voice from the demo (Priority: P2)

The presenter wants to know which engines exist and choose a Spanish voice. The demo shows the engine
the connected service is running as the active one, lets the presenter pick among that engine's
voices, and lists the other engine as unavailable with a hint on how to restart the service with it.
To compare engines, the presenter restarts the service with the other engine and reloads the demo;
the demo never switches the engine itself.

**Why this priority**: Side-by-side comparison is the main reason to have two engines, but the demo
is already useful with the engine simply shown (P1).

**Independent Test**: With the service running VibeVoice, play the same text with two different
voices and confirm each run is voiced by the selected voice; confirm Kokoro is shown as unavailable.

**Acceptance Scenarios**:

1. **Given** the service runs VibeVoice, **When** the presenter selects a voice and plays, **Then**
   the speech uses that voice and the demo labels engine and voice.
2. **Given** the service runs one engine, **When** the presenter views the engine selector, **Then**
   the other engine is shown as unavailable, cannot be selected, and a short reason says which engine
   the service runs and how to restart it with the other.
3. **Given** the voice list is open, **When** the presenter views it, **Then** it only contains
   Spanish voices valid for the engine the service runs.

---

### User Story 3 - Understand VibeVoice-specific failures and delays (Priority: P3)

VibeVoice is slower to start and may be unavailable (model not downloaded, no verified Spanish
voice, not ready yet). The presenter sees a clear "preparing" state while waiting for the first audio
and a plain-language message with a next step if the engine refuses, and can retry without reloading.

**Why this priority**: Improves robustness of live demos but does not block the core flow.

**Independent Test**: Start the service with VibeVoice unverified or its model missing, press play,
and confirm a readable message appears and the demo remains usable.

**Acceptance Scenarios**:

1. **Given** VibeVoice takes longer than Kokoro to emit its first audio, **When** the presenter
   plays, **Then** the demo shows a "preparing speech" state until audio begins.
2. **Given** the engine refuses to synthesize, **When** the presenter plays, **Then** a clear message
   explains it and the controls return to ready.
3. **Given** the presenter presses stop during the preparing state, **When** stop is pressed,
   **Then** the request is cancelled and the demo is ready again.

---

### Edge Cases

- Service address points to a service running an engine different from the one the presenter
  expects: the demo shows the engine actually in use, never an assumed one.
- Presenter tries to use an engine the running service is not configured for: it is not selectable;
  the demo names the engine in use and how to restart the service with the other, and nothing is
  played.
- Engine or voice list cannot be obtained (older service, unreachable): the demo falls back to the
  current single-engine behavior with the default voice and says so.
- VibeVoice's audio sample rate differs from Kokoro's: playback and teleprompter timing remain
  correct for either.
- Text is empty or over the length limit: same rejection messages as today.
- Presenter changes voice while a playback is in progress: playback is stopped first.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The demo MUST play Spanish text spoken by the VibeVoice engine, with incremental
  playback and teleprompter tracking equivalent to the Kokoro experience.
- **FR-002**: The demo MUST display the engine, and the voice, that is speaking, taken from what the
  service reports for the request, not from the demo's own assumption.
- **FR-003**: The demo MUST let the presenter choose a voice, among those of the engine the service
  runs, before playing. It MUST NOT switch or restart the service's engine.
- **FR-004**: The demo MUST offer only the engine and voices the connected service reports as
  available, and MUST show the other engine as disabled with a reason that says which engine the
  service runs and how to restart it with the other.
- **FR-005**: The demo MUST keep working unchanged against a Kokoro-only service, and when engine or
  voice information is unavailable it MUST fall back to default behavior and tell the presenter.
- **FR-006**: The demo MUST show a "preparing speech" state between pressing play and the first
  audio, and the stop control MUST work during that state.
- **FR-007**: The demo MUST present plain-language messages for VibeVoice failures (engine not
  ready, no verified Spanish voice, engine failure, unsupported engine or voice), each with a way to
  retry without reloading.
- **FR-008**: The demo MUST remain a client of the existing service interface only and MUST NOT load
  or run any engine itself.
- **FR-009**: The demo MUST keep all audio Spanish; no non-Spanish voice may be offered.
- **FR-010**: Existing demo behavior (stop, state indicator, input validation, configurable service
  address, localhost-only binding) MUST be preserved.

### Key Entities

- **Engine option**: A speech engine the presenter can pick; has a display name, an availability
  state with a reason when unavailable, and a list of voices.
- **Voice option**: A Spanish voice belonging to one engine; has a display name.
- **Playback session**: One play request; records the engine and voice actually used, shown to the
  presenter.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: A presenter can play a Spanish text with VibeVoice from a running service in under
  1 minute from opening the demo, with no code or configuration edits beyond choosing the service.
- **SC-002**: In 100% of tested plays, the engine and voice shown on screen match the ones that
  produced the audio.
- **SC-003**: Teleprompter drift with VibeVoice stays within the same tolerance accepted for Kokoro
  (no more than one sentence ahead or behind the audio in 95% of tested texts).
- **SC-004**: After pressing play, the presenter sees a visible state change within 1 second, and
  stopping silences audio within 1 second in 95% of attempts, for both engines.
- **SC-005**: In every tested VibeVoice failure case (model missing, no verified voice, engine
  failure, unsupported selection), the presenter sees an explanatory message and can retry without
  reloading the page.
- **SC-006**: All existing demo tests and Kokoro demo scenarios still pass unchanged.

## Assumptions

- The service is started separately by the operator with one engine at a time; the demo does not
  start, stop, or switch the service's engine process (confirmed in clarification). Comparing engines
  means restarting the service with the other engine and reloading the demo.
- VibeVoice is available only over the WebSocket transport, which is what the demo already uses.
- Voices are the Spanish-verified preset voices of each engine; custom or cloned voices are out of
  scope.
- Single local user, localhost-only, no authentication, as in the existing demo.
- Any extra service capability needed to list engines and voices is limited to read-only
  information and does not change existing client behavior.
- Mobile layout, side-by-side playback of both engines, and connecting to two services at once are out of scope.
