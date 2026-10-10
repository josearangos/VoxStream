# Quickstart: Validate gRPC Streaming

Prerequisites: feature 001 set up (`uv sync --extra verify`, `uv run voxstream download-models`,
`uv run voxstream verify-voices`). Commands describe the validation flow and work once the tasks
are implemented. Contract details: [grpc-protocol.md](contracts/grpc-protocol.md).

## 1. Install and (re)generate stubs

```bash
uv sync --extra verify
scripts/gen_proto.sh        # only after editing proto/voxstream/v1/voxstream.proto
```

## 2. Run the service (both transports on by default)

```bash
uv run voxstream serve
# prints: WebSocket ws://127.0.0.1:8765/v1/stream   gRPC 127.0.0.1:50051
curl http://127.0.0.1:8765/readyz
```

Single transport:

```bash
VOXSTREAM_ENABLE_WEBSOCKET=false uv run voxstream serve   # gRPC only; /readyz still on :8765
VOXSTREAM_ENABLE_GRPC=false uv run voxstream serve        # WebSocket only
```

## 3. Stream text and hear audio over gRPC

```bash
uv run python examples/grpc_client.py --simulate-llm \
  "Hola, soy tu asistente. Hoy hace un buen día para aprender algo nuevo."
```

Expected: audio starts before the last text piece is sent and a `completed` event is printed.

## 4. Cancellation, voices and errors

```bash
uv run python examples/grpc_client.py --cancel-after-chunks 3 "<long Spanish text>"
uv run python examples/grpc_client.py --voice em_alex --output alex.wav "Mañana iremos a la montaña."
uv run python examples/grpc_client.py --voice af_heart "Hello"   # expect UNSUPPORTED_VOICE
```

## 5. Cross-transport checks

```bash
# Terminal A: long request over WebSocket; terminal B: gRPC request while A runs -> BUSY
uv run python examples/ws_client.py "<long Spanish text>"
uv run python examples/grpc_client.py "Hola"
```

## 6. Automated tests

```bash
uv run pytest                  # unit + contract (both transports) + integration, mock engine
uv run pytest -m model         # Kokoro-backed, both transports
uv run ruff check . && uv run mypy src
```

## Success checks (map to the spec)

| Check | Spec |
|-------|------|
| Step 3 audio starts before last piece | SC-003, FR-004 |
| Step 4 cancel prints `cancelled`; unsupported voice prints `UNSUPPORTED_VOICE` | SC-001, FR-005, FR-006 |
| Step 5 second request is `BUSY` | SC-005, FR-008 |
| `pytest` contract suite green for `websocket` and `grpc` | SC-001, FR-015 |
| Same text → identical audio bytes on both transports (integration test) | SC-002 |
| `grpc_client.py` works from README alone in < 5 minutes | SC-007 |
| Contract doc maps every WebSocket message | SC-008 |
