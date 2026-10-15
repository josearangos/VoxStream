# Research: VibeVoice in the Gradio demo

## R1 — How the demo learns the service's engine and voices
- **Decision**: `GET /readyz` on the service's HTTP port, derived from `DEMO_SERVICE_URL`
  (`ws://h:p/v1/stream` → `http://h:p/readyz`; `wss` → `https`). Body: `ready`, `engine`,
  `voices`, optional `reason`. A 503 with a body is parsed the same as 200 (not-ready is data).
- **Rationale**: Already exists, read-only, works when the engine is not ready (so the reason can be
  shown), needs no WebSocket session. Called with stdlib `urllib` in a worker thread, 2 s timeout.
- **Alternatives**: WebSocket `capabilities` message (richer, but needs a connection and gives no
  not-ready reason; kept as a possible later source); a new service endpoint (rejected, FR-008).

## R2 — Engine selector under "no switching"
- **Decision**: A non-interactive radio showing the active engine selected, plus a hint line for the
  other engine: "Kokoro is not running. The service runs VibeVoice; restart it with
  `VOXSTREAM_ENGINE=kokoro` and refresh." Known engines: `kokoro`, `vibevoice` (display names only).
- **Rationale**: Gradio radios cannot disable one choice; a read-only radio plus text meets
  "shown as unavailable with reason" (FR-004) without implying switching.
- **Alternatives**: interactive radio that errors on the wrong pick (rejected: invites the failure).

## R3 — Voice selection
- **Decision**: Dropdown filled from `voices`; the first voice is preselected; the chosen voice is
  sent in `start`. `start` also carries the active engine name so that a service restarted with
  another engine after page load fails with `UNSUPPORTED_ENGINE` instead of speaking with the wrong
  engine. A refresh button re-reads `/readyz`.
- **Rationale**: Uses existing protocol fields; guarantees SC-002 (shown = used).

## R4 — What is displayed as "speaking with"
- **Decision**: From the `started` stream descriptor (`engine`, `voice`), shown once playback
  starts and kept after it ends. Before that, the pre-play line shows the readiness info.
- **Rationale**: Reports what the service did, not what the demo assumed (FR-002).

## R5 — "Preparing speech" state
- **Decision**: No new state-machine state. While the session is Playing but no audio chunk has
  arrived (`t0 is None`), the status text reads "Preparing speech…". `started` is sent before
  synthesis, so this window is exactly VibeVoice's slow first audio. Stop already works in it.
- **Rationale**: Minimal; avoids touching allowed transitions.

## R6 — Error and not-ready messages
- **Decision**: Keep the rule that unknown codes never echo server text. Add specific mapped
  messages: `ENGINE_UNAVAILABLE` ("not ready; if this is VibeVoice, check that its model is
  downloaded and its voices are verified, then Refresh"), `UNSUPPORTED_ENGINE` (service runs another
  engine; refresh), `UNSUPPORTED_VOICE` (refresh voices). The `/readyz` `reason` is shown verbatim,
  truncated to 200 chars, in the engine info line only (it is a fixed server-side sentence that
  contains no user text).
- **Alternatives**: Never show `reason` (rejected: the "no verified Spanish voice" reason is the
  most useful next step).

## R7 — Fallback when info is unavailable
- **Decision**: If `/readyz` is unreachable, 404 or malformed: engine shown as "unknown", voice
  dropdown disabled with "Service default", `start` sent without voice/engine (today's behavior), and
  a one-line note says why.
- **Rationale**: FR-005; keeps older services and the existing tests working.

## R8 — Sample rate and timing
- **Decision**: No change. Sample rate and channels already come from `started`; the timeline is
  estimated from audio received and rescaled on completion, independent of engine.
