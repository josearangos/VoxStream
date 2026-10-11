# Measurements

Hardware: Apple M2 Pro, 16 GB, macOS 26.2. Python 3.12.11, kokoro-onnx 0.6.1, onnxruntime 1.31.0,
websockets 17.2. Kokoro `kokoro-v1.0.onnx` (full precision), CPU provider, voice `ef_dora`,
localhost client. Script: `scripts/measure_stream.py` (20 consecutive requests, 175 Spanish
characters, one request at a time). Server and client share the machine.

| Metric | Median | p95 | Target |
|--------|-------:|----:|--------|
| Time to first audio after the piece that completes sentence 1 (warm) | 430 ms | 448 ms | < 1 s (SC-001) |
| Time to first audio, first request after start (cold, includes model load) | 1.5 s | - | informational |
| Real-time factor (generation / audio) | 0.28 | 0.29 | < 1.0 (SC-002) |
| Generation time per request | 2.96 s | 3.06 s | - |
| Delivery time (first to last frame) | 2.56 s | 2.66 s | - |
| Median inter-frame gap | 0.27 ms | 0.27 ms | - |
| Largest inter-frame gap (between segments) | 1.28 s | 1.32 s | see note |
| Peak server RSS over 20 requests | 621 MB | - | < 4 GB (SC-009) |
| Cancel latency (audio stops after `cancel`) | 3 ms | - | < 500 ms (SC-004) |

Note: the largest gap occurs where a client that sends all text at once waits for the next
segment's synthesis; with real-time playback the buffered audio (about 2.5 s of lead) covers it,
because the real-time factor is below 1.

Peak memory is the server process RSS sampled after each request, not a continuous trace.
Cold-start requests exceed 1 s; warm the service with one request (or `/readyz` plus a short
dummy request) before latency-sensitive use.

## gRPC versus WebSocket (feature 002, sanity check)

Same machine, model, voice, text and script (`scripts/measure_stream.py --transport {websocket,grpc}`),
20 consecutive requests per transport against one running service (WebSocket first, then gRPC).
**Local loopback only, not a remote network.** This is a sanity check; the formal benchmark is the
next feature.

| Metric (median / p95) | WebSocket | gRPC |
|-----------------------|----------:|-----:|
| Time to first audio after sentence 1 | 431 / 506 ms | 437 / 491 ms |
| Real-time factor | 0.28 / 0.34 | 0.28 / 0.33 |
| Generation time per request | 2.97 / 3.54 s | 2.98 / 3.49 s |
| Delivery time (first to last frame) | 2.56 / 2.88 s | 2.54 / 3.11 s |
| Median inter-frame gap | 0.27 / 0.28 ms | 0.14 / 0.21 ms |
| Peak server RSS (sampled after each request) | 686 MB | 583 MB (same process, after the WebSocket run) |

Both transports stayed far below the 4 GB ceiling over 20 requests with no out-of-memory failure
(SC-006). The gRPC run followed the WebSocket run in the same process, so its RSS and cold-start
numbers are not comparable.

## README-only gRPC run (SC-007)

Same Mac, Kokoro `ef_dora`, run on 2026-10-10 following the README commands. Dependencies and
models were already cached, so `uv sync` and `download-models` were near-instant; a first-time
download (~350 MB) adds network time that is not included here.

| Step | Time |
|------|-----:|
| `uv sync` (cached) | 1.3 s |
| `uv run voxstream serve` until `/readyz` answers | 0.5 s |
| `examples/grpc_client.py --simulate-llm "Hola, soy tu asistente."` (cold: first request loads the model) | 2.6 s (first audio 2.5 s) |
| Total after install | about 3.1 s |

This is well under the 5-minute target (SC-007) once models are downloaded.
