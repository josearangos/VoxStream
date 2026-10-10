# Research: Gradio Teleprompter Demo

## R1 — UI framework and audio output
- **Decision**: Gradio 6.x `Blocks` with a streaming `gr.Audio` output (`streaming=True`,
  `autoplay=True`) fed by a generator that yields WAV-wrapped 16-bit PCM chunks.
- **Rationale**: Requested by the user. Verified in Gradio 6.30 source: streamed `bytes` chunks that
  are 16-bit WAV are read with the standard library, then re-encoded for the browser by one ffmpeg
  process per stream. Service frames are already 24 kHz mono `pcm_s16le`, so only a WAV header
  must be added per chunk.
- **Alternatives**: Custom JS Web Audio page (more control, but not Gradio, and defeats the point
  of the demo); saving a WAV and playing at the end (not real time).
- **Consequence**: ffmpeg must be installed (macOS: `brew install ffmpeg`); documented in
  quickstart. Browser autoplay needs a prior user gesture — the Start click provides it.

## R2 — What drives the teleprompter position
- **Decision**: Drive highlighting from what the browser is playing, not from when frames arrive.
  Primary signal: the audio component's reported `playback_position` (Gradio updates it as audio
  plays). Fallback if it is not reliable for streamed output: wall-clock time since the first chunk
  was yielded plus a configurable offset (`DEMO_PLAYBACK_LEAD_MS`).
- **Rationale**: The service produces audio faster than real time, so frame arrival time runs
  ahead of what the user hears; highlighting by arrival would race ahead (violates SC-003).
- **Alternatives**: Highlight per received frame (too early); pace server yields to real time
  (works, but ties the relay to the clock and hurts cancel latency).
- **T018 outcome (2026-10-10)**: `gr.Audio.playback_position` is a client-reported prop with no
  documented update rate for streamed output, and it could not be verified without a browser
  session. Decision: use the wall-clock fallback — elapsed time since the first yielded chunk plus
  `DEMO_PLAYBACK_LEAD_MS`, capped at the audio received so far — driven by a `gr.Timer` (0.2 s).
  Because the service synthesizes faster than real time, `completed` (and the exact audio length)
  usually arrives early, so the rescale removes most drift. `Timeline.reanchor` exists and is tested
  but is unused until a real position signal is available. SC-003 stays at "within ~1 s", to be
  confirmed by ear (T020).
- **Open check (resolved above)**: Confirm during implementation (task: spike) which signal is available for streamed
  output; the timeline module is signal-agnostic (takes seconds, returns word index).

## R3 — Word timing estimate
- **Decision**: Split text into words; give each word a weight = its character count plus a
  pause weight for trailing punctuation (comma, sentence end, line break). Initial duration per
  weight comes from a configurable speech-rate constant (default tuned on the Kokoro Spanish
  voice, verified in quickstart). When `completed` reports total `audio_ms`, scale the whole
  timeline to match exactly, so the final word ends with the audio.
- **Rationale**: The protocol exposes no word timing and must not change (FR-012). Scaling at
  completion removes drift for the tail. While streaming, the timeline uses the rate constant and
  is re-anchored whenever the playback signal reports the audio position (see R2): the remaining
  words are re-timed so the estimate tracks the elapsed audio instead of accumulating error. If the
  T018 spike shows that no usable position signal exists, SC-003 is relaxed to "within 1 s on
  average, exact at completion".
- **Alternatives**: Forced alignment with a speech-recognition model (accurate but heavy and a new
  model dependency); uniform spacing by characters only (ignores punctuation pauses, drifts more).
- **Accepted limit**: Estimated, not exact (spec Assumptions); SC-003 is measured in quickstart.

## R4 — How the text is sent
- **Decision**: Send the full text as a single `text` message followed by `end`.
- **Rationale**: The user asked for a plain text input; the service already segments by sentence and
  streams audio incrementally (001 scenario 4). Simulating LLM-style small pieces is a client
  option for the existing `examples/ws_client.py`, not needed here.
- **Alternatives**: Piecewise sending (adds pacing code, no user-visible benefit).

## R5 — Bounded relay and cancellation
- **Decision**: Consume frames from the WebSocket and yield each to Gradio as it arrives; no
  unbounded list of audio is kept (only counters for duration). Stop triggers the generator's
  cancellation, which sends `cancel` and closes the connection; client disconnect does the same.
- **Rationale**: Constitution V/VIII; service-side `cancel`/disconnect already free the slot.
- **Alternatives**: Collect all audio then yield (not real time, unbounded).

## R6 — Error mapping
- **Decision**: A table maps each protocol v1 error code (`BUSY`, `TEXT_TOO_LONG`,
  `UNSUPPORTED_VOICE`, `ENGINE_UNAVAILABLE`, timeouts, etc.) and connection failures to a
  plain-language message and a "can retry" hint; unknown codes get a generic message that does not
  echo raw server text.
- **Over-length check**: The pre-check uses the static `DEMO_MAX_TEXT_CHARS` (default 2,000,
  matching the service default). The service's `TEXT_TOO_LONG` error is authoritative if the two
  differ, and it is shown with the same message.

## R7 — Localhost only
- **Decision**: Launch Gradio on `127.0.0.1` with sharing off; service URL from `DEMO_SERVICE_URL`
  (default `ws://127.0.0.1:8765/v1/stream`).
- **Rationale**: Constitution XII; the demo sends user text only to the configured local service.
