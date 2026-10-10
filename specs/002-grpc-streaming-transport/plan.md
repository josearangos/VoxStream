# Implementation Plan: gRPC Streaming Transport with WebSocket Parity

**Branch**: `002-grpc-streaming-transport` | **Date**: 2026-10-10 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `/specs/002-grpc-streaming-transport/spec.md`

## Summary

Add a second, independent transport (gRPC) beside the existing WebSocket one, on top of the same
engine, session pipeline, admission control and voice gate. A client opens one bidirectional
gRPC call per request, streams text pieces up and receives ordered audio chunks plus control
events down, with the same error codes, limits and cancellation semantics as WebSocket.

Two small refactors make this possible without leaking transport details into the core (FR-007):

1. `core/session.py` currently imports the WebSocket frame encoder and emits pre-encoded bytes. It
   will emit transport-neutral audio frames (`request_id`, `sequence`, `last`, `pcm`); the
   WebSocket adapter encodes them with the existing binary header, the gRPC adapter puts them in a
   protobuf message.
2. Request-opening logic that lives in `VoxStreamServer` (engine/language/voice validation,
   readiness, admission, lazy engine start, voice default) moves into a shared
   `core/service.py`. Both transports call it, so the concurrency limit and readiness are
   service-wide by construction (FR-008, FR-012).

Both transports are enabled by default (clarification); health stays on the existing HTTP
endpoints. The existing contract tests are parametrized over a transport-neutral test client so one
suite proves parity (FR-015). See [research.md](research.md) for decisions.

## Technical Context

**Language/Version**: Python 3.12 (unchanged; pinned through `uv`)

**Primary Dependencies**: adds `grpcio` (asyncio server, `grpc.aio`) at runtime; `protobuf`
(already installed transitively, now declared). Dev: `grpcio-tools` to regenerate stubs. Existing:
`websockets`, `pydantic`, `pydantic-settings`, `kokoro-onnx`, `onnxruntime`, `numpy`. Versions
resolved by `uv` at implementation time (`grpcio` 1.84.0 resolves for Python 3.12 on macOS arm64).

**Storage**: N/A (no new files besides generated stubs committed to the repo)

**Testing**: pytest; contract tests parametrized by `transport` (`websocket`, `grpc`) and `engine`
(`mock`, `kokoro` marked `model`); WebSocket-only wire tests (malformed JSON, binary frames) stay
WebSocket-only; gRPC-only wire tests cover protobuf framing and call-level cancellation.

**Target Platform**: macOS 26 on Apple Silicon (M2 Pro, 16 GB); CPU baseline

**Project Type**: single Python package exposing local network services plus a CLI

**Performance Goals**: same as 001: first audio under 1 s after the text piece that completes the
first sentence; cancel stops audio within 500 ms; per-chunk gRPC delivery overhead is measured in T045, not
asserted (formal comparison is the next feature).

**Constraints**: both endpoints bind to 127.0.0.1 by default; one active request service-wide
(shared); 2,000 characters per request; 64 KiB max inbound message on both transports; bounded
text and audio buffers; no network access during inference.

**Scale/Scope**: one local client at a time; one engine plus mock; two transports. Benchmark
harness, VibeVoice, TLS and authentication are out of scope.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Status | How the plan satisfies it |
|-----------|--------|---------------------------|
| I. Real-time streaming first | Pass | Same `Session` pipeline; bidirectional stream so audio flows while text is still arriving; terminal event per request; bounded queues. |
| II. Engine-agnostic | Pass | gRPC servicer talks to `core/service.py` and `TTSEngine` only; no Kokoro imports in the transport. |
| III. Transport parity and fair benchmarking | Pass | Closes the gap deferred in 001. Same engine instance, same session, same audio format, same limits; one parametrized contract suite; mapping table in [contracts](contracts/grpc-protocol.md). Timing stays split between generation and delivery per transport (`transport` field in logs) to enable the benchmark feature. |
| IV. Local-first / Apple Silicon | Pass | No new runtime services; `grpcio` ships macOS arm64 wheels; localhost bind default. |
| V. Memory-constrained | Pass | One loaded model shared by both transports; bounded outbound queue; 64 KiB message cap. |
| VI. Explicit contracts | Pass | `.proto` plus a message-by-message mapping to the WebSocket protocol; `streaming_mode` reported in `Started` and capabilities. |
| VII. Engine compatibility | Pass | No engine changes. |
| VIII. Reliability | Pass | Same validation, limits, timeouts, admission; call cancel/drop releases the slot deterministically; backpressure via HTTP/2 flow control and bounded queues. |
| IX. Quality / testability | Pass | Typed code; shared contract tests for both transports; generated stubs excluded from lint/mypy but regeneration scripted. |
| X. Observability | Pass | Correlation id per request; `transport` added to log context; no text/audio in logs. |
| XI. Simplicity | Pass | Same process, one extra listener, no proxy or broker. Extracting `core/service.py` removes duplication rather than adding layers. |
| XII. Security / privacy | Pass | Localhost default; non-local bind needs the same opt-in; insecure channel documented as local-only; no TLS (out of scope, documented). |
| XIII. Documentation | Pass | gRPC contract, example client, README section; tested vs planned stated. |
| XIV. Spanish audio | Pass | Same voice gate and `es`-only language check via the shared service. |

No violations; Complexity Tracking is empty. **Post-design re-check (after Phase 1): still
passes.** Watch item: the `Session` refactor touches 001 code, so the existing WebSocket suite must
stay green unchanged before any gRPC code is added.

## Project Structure

### Documentation (this feature)

```text
specs/002-grpc-streaming-transport/
├── plan.md
├── research.md
├── data-model.md
├── quickstart.md
├── contracts/
│   ├── grpc-protocol.md       # semantics + WebSocket mapping table + error mapping
│   └── voxstream.proto        # wire schema (source of truth copied to proto/)
├── checklists/requirements.md
└── tasks.md                   # created later by /speckit-tasks
```

### Source Code (repository root)

```text
proto/voxstream/v1/voxstream.proto        # new: wire schema
scripts/gen_proto.sh                      # new: regenerate stubs with grpcio-tools
src/voxstream/
├── config.py                  # + enable_websocket, enable_grpc, grpc_port
├── app.py                     # NEW: composes service + enabled transports
├── core/
│   ├── service.py             # NEW: shared admission, engine lifecycle, readiness, open_session
│   ├── session.py             # CHANGED: emits AudioFrame objects, no websocket import
│   └── frames.py              # NEW: transport-neutral AudioFrame dataclass
├── transports/
│   ├── health.py              # NEW: minimal HTTP /healthz,/readyz when WebSocket is disabled
│   ├── websocket/
│   │   ├── framing.py         # encode/decode stays here, now used only by this transport
│   │   └── server.py          # CHANGED: delegates to core/service.py
│   └── grpc/
│       ├── gen/               # generated *_pb2.py, *_pb2_grpc.py (committed)
│       ├── server.py          # NEW: grpc.aio server, Stream + GetCapabilities servicer
│       └── convert.py         # NEW: AudioFrame/Result/Error <-> protobuf
└── cli.py                     # CHANGED: starts enabled transports, prints both endpoints
examples/
├── ws_client.py
└── grpc_client.py             # NEW: mirrors ws_client flags
tests/
├── unit/                      # + test_grpc_convert.py, test_service.py
├── contract/                  # parametrized by transport via neutral client
└── integration/               # + test_grpc_streaming.py, test_both_transports.py
```

**Structure Decision**: keep the single-package src layout. `core` no longer imports anything from
`transports`; each transport owns its wire encoding and depends only on `core` and `engines.base`.
`transports/grpc/` sits beside `transports/websocket/` exactly as 001 anticipated.

## Complexity Tracking

No constitution violations to justify.
