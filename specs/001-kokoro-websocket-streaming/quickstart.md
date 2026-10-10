# Quickstart: Validate Kokoro Spanish Streaming over WebSocket

Prerequisites: macOS on Apple Silicon, `uv` installed, network access only for the first install
and model download. Python 3.12 is installed by `uv`. See [research.md](research.md) for versions.

Commands below describe the validation flow; they work once the tasks are implemented.

## 1. Setup

```bash
uv sync --extra verify            # creates .venv with Python 3.12 and locked dependencies
uv run voxstream download-models  # fetches kokoro-v1.0.onnx and voices-v1.0.bin into models/
```

## 2. Verify the voices produce Spanish (gate)

```bash
uv run voxstream verify-voices            # writes verification/voice-verification.json
uv run voxstream verify-voices --signoff ef_dora   # after listening once
```

Expected: at least one voice with `passed: true`. If none pass, the service reports not ready and
the feature is blocked (see risks in research.md).

## 3. Run the service

```bash
uv run voxstream serve                    # binds to 127.0.0.1:8765
curl http://127.0.0.1:8765/readyz         # expect 200 and the execution provider
```

## 4. Stream text and hear audio

```bash
uv run python examples/ws_client.py --simulate-llm \
  "Hola, soy tu asistente. Hoy hace un buen día para aprender algo nuevo."
```

The client sends the text in small pieces with short pauses (simulating an LLM), saves or plays
the audio, and prints time to first audio. Expected: audio begins before the last piece is sent
(SC-010) and the client prints a `completed` message.

## 5. Cancellation and errors

```bash
uv run python examples/ws_client.py --cancel-after-chunks 3 "<long Spanish text>"
uv run python examples/ws_client.py --voice af_heart "Hello"   # expect UNSUPPORTED_VOICE
```

## 6. Automated tests

```bash
uv run pytest                      # unit + contract + integration with the mock engine
uv run pytest -m model             # Kokoro-backed tests (needs models/, slower)
uv run ruff check . && uv run mypy src
```

## Success checks (map to the spec)

| Check | Spec |
|-------|------|
| First audio before last text piece sent; ordered, gap-free frames | SC-001, SC-003, SC-010 |
| Cancel stops audio within 500 ms; new request accepted | SC-004 |
| Slow-client test keeps buffers within bound | SC-005 |
| Each error code reproduced with a structured message | SC-006 |
| Only verified voices offered; non-Spanish rejected | SC-007 |
| Same contract tests pass on mock and Kokoro | SC-008 |
