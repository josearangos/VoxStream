# VoxStream

Local Spanish text-to-speech streaming service. Clients stream text over a WebSocket and receive
PCM audio frames while the text is still arriving. The engine is Kokoro-ONNX (CPU), behind a common
`TTSEngine` interface.

## Installation

Requires macOS on Apple Silicon and [`uv`](https://docs.astral.sh/uv/). Python 3.12 is installed by `uv`.

```bash
uv sync --extra verify            # add --extra verify only if you will run voice verification
uv run voxstream download-models  # kokoro-v1.0.onnx + voices-v1.0.bin into models/ (~350 MB)
uv run voxstream verify-voices    # writes verification/voice-verification.json
uv run voxstream verify-voices --signoff ef_dora   # after listening to the voice once
```

## Supported versions
Tested on macOS 26.2 (Apple M2 Pro, 16 GB), Python 3.12.11, `kokoro-onnx` 0.6.1,
`onnxruntime` 1.31.0. Other platforms and Python versions are untested.

## Configuration
Environment variables (prefix `VOXSTREAM_`, optional `.env`):

| Variable | Default | Meaning |
|----------|---------|---------|
| `HOST` / `PORT` | `127.0.0.1` / `8765` | Bind address; non-loopback needs `ALLOW_NON_LOCAL_BIND=true` |
| `ENGINE` | `kokoro` | `kokoro` or `mock` |
| `MAX_TEXT_CHARS` | `2000` | Total characters per request |
| `REQUEST_TIMEOUT_S` / `IDLE_TIMEOUT_S` | `120` / `15` | Request and idle timeouts |
| `MAX_CONCURRENT_REQUESTS` | `1` | Service-wide active requests |
| `FRAME_MS` | `100` | Audio frame duration |
| `AUDIO_QUEUE_FRAMES` | `8` | Buffered frames before synthesis pauses |
| `MAX_PENDING_CHARS` | `120` | Fallback segment cut length |
| `EXECUTION_PROVIDER` | `cpu` | `cpu` or `coreml` (CPU recommended) |
| `MODELS_DIR` | `models` | Model files location |
| `VERIFICATION_FILE` | `verification/voice-verification.json` | Voice gate file |
| `DEFAULT_VOICE` | first verified | Voice used when the client omits one |

## Running
```bash
uv run voxstream serve
curl http://127.0.0.1:8765/readyz
uv run python examples/ws_client.py --simulate-llm "Hola, soy tu asistente."
```

## Protocol
WebSocket at `ws://127.0.0.1:8765/v1/stream`: JSON text frames for control (`start`, `text`, `end`,
`cancel`, `capabilities`; replies `started`, `completed`, `cancelled`, `error`) and binary frames for
audio (16-byte request id, uint32 sequence, flags, PCM s16le 24 kHz mono). Full contract:
[`specs/001-kokoro-websocket-streaming/contracts/`](specs/001-kokoro-websocket-streaming/contracts/).
gRPC client examples are delivered with the gRPC feature.

## Troubleshooting
- **`/readyz` returns 503**: the reason is in the JSON body. Missing models: run `download-models`.
  No verified voice: run `verify-voices`; re-run it if the model file changed.
- **First request is slow (~1.5 s)**: the model loads lazily on the first request.
- **espeak errors**: the phonemizer library ships with `espeakng-loader`; reinstall with `uv sync`.
- **Out of memory (`OUT_OF_MEMORY`)**: close other applications; typical use is about 0.6 GB.
- **`BUSY`**: only one request runs at a time; retry after the active one ends.

## Tested versus planned
- Tested: WebSocket streaming, cancel, errors, backpressure, voice verification and health checks,
  with the mock engine (default test run) and Kokoro (`pytest -m model`).
- Experimental: Core ML provider (works, not faster; see `docs/decisions.md`), the int8 model
  (needs its own verification).
- Planned, not built: gRPC transport, other engines (e.g. VibeVoice).

## Development
`scripts/check.sh` runs ruff, mypy and the default tests. Measurements: `docs/measurements.md`.
