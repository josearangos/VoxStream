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
