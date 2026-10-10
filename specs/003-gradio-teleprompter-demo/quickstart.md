# Quickstart: Gradio Teleprompter Demo

## Prerequisites
- macOS, Python 3.12, `uv`, and ffmpeg (`brew install ffmpeg`) — Gradio's streaming audio needs it.
- Kokoro model files in `models/` as described in the main README.

## Run
```bash
# terminal 1 — the service
uv run voxstream

# terminal 2 — the demo (installs the optional demo extra)
uv run --extra demo python -m demo.app
# open http://127.0.0.1:7860
```
Settings (optional): `DEMO_SERVICE_URL`, `DEMO_HOST` (default 127.0.0.1), `DEMO_PORT`,
`DEMO_PLAYBACK_LEAD_MS`, `DEMO_MAX_TEXT_CHARS` (keep it equal to the service's
`VOXSTREAM_MAX_TEXT_CHARS`).

## Validation scenarios
1. **Story 1**: Paste a multi-sentence Spanish paragraph, press Start. Speech starts within ~2 s
   and plays to the end; status ends at Finished.
2. **Story 2**: With a ~1-minute text, watch the highlight. It moves word by word, stays within ~1 s
   of the audio, the view scrolls on its own, and every word is spoken at the end. (Record any
   drift to retune `DEMO_PLAYBACK_LEAD_MS` or the speech-rate constant.)
3. **Empty input**: Clear the box, press Start — message shown, nothing sent.
4. **Stop**: Press Stop mid-playback — audio stops within ~1 s; Start works again.
5. **Service down**: Stop the service, press Start — "Can't reach…" message, no stuck state.
6. **Busy**: Start playback from `examples/ws_client.py` and the demo together — demo shows the
   busy message.
7. **Too long**: Paste more than 2,000 characters — limit message, nothing sent.

## Automated tests
```bash
uv run --extra demo pytest tests/demo        # no model download; uses the mock engine
```

## Status notes (2026-10-10)
- Automated: `tests/demo` (45 tests) pass; ruff/format/mypy clean; `src/voxstream` unchanged.
- Smoke (scripted via `gradio_client` against a local service): first streamed audio update reached
  the client ~1.4 s after Start. Not measured by ear/browser.
- **Not yet done (needs a human with a browser and audio):** scenarios 1–2 by ear (drift, SC-003),
  Stop latency over ~10 attempts (SC-004), and scenarios 4–7 in the UI (T013, T020, T026, T031).
  `DEMO_PLAYBACK_LEAD_MS` and `DEMO_SPEECH_RATE_CHARS_PER_S` defaults are untuned.
