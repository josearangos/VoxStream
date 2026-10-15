# Quickstart: validating VibeVoice in the demo

## Prerequisites
- Feature 004 prerequisites (VibeVoice model, verified voices, `VOXSTREAM_VIBEVOICE_DEVICE=mps`).
- `ffmpeg`, and `uv sync --extra demo` (plus `--extra vibevoice --extra verify` for the real engine).

## 1. Default tests (no model)
`uv run pytest tests/demo` — covers readiness parsing, fallback, voice/engine in `start`, Started
engine/voice, "Preparing speech…" status, and error messages against the mock engine.

## 2. VibeVoice end to end (US1, SC-001..SC-004)
1. `VOXSTREAM_ENGINE=vibevoice VOXSTREAM_ENABLE_GRPC=false uv run voxstream serve`
2. `uv run --extra demo python -m demo.app`, open http://127.0.0.1:7860
3. Expect info line "VibeVoice · ready" and a voice list (e.g. `sp-Spk2_woman`).
4. Press Start: status "Preparing speech…" then "Playing"; audio is Spanish; the teleprompter
   follows; "Speaking with VibeVoice · <voice>" matches the dropdown.

## 3. Voice choice and engine hint (US2)
Play the same text with two voices; confirm each run uses its voice. Confirm the hint reads that
Kokoro is not running and how to restart with it. Restart the service with Kokoro, press Refresh,
confirm "Kokoro" and its voices; Start behaves as before (SC-006).

## 4. Failures (US3, SC-005)
- Stop the service: Start shows the unreachable message; Refresh shows fallback mode.
- Start the service with VibeVoice but no model/unverified voices: info line shows the reason; Start
  shows the not-ready message; fix and Refresh without reloading the page.
- Press Stop during "Preparing speech…": audio and request stop, controls return to ready.
- Restart the service with the other engine without refreshing, then Start: message says the
  service runs another engine; Refresh recovers.
