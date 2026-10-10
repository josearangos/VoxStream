# Decisions

## Streaming and buffering
- **Segmentation**: sentence ends (`. ! ? … ;`, newline), Spanish abbreviations and decimals not split,
  a `.` at the end of the buffer waits for the next character. Fallback cut when pending text reaches
  120 characters: last comma if it lies in the second half, otherwise the last space. Chosen to keep
  segments short (low first-audio delay and cancel granularity) without cutting inside words.
- **Frame size 100 ms** (4,800 bytes): small enough for smooth playback and cancellation, large enough
  to keep per-frame overhead (21-byte header) under 0.5%.
- **Queue bounds**: 4 pending segments, 8 audio frames (about 0.8 s), inbox of 8 messages per
  connection. A full inbox stops socket reads so TCP backpressure reaches the client.
- **PCM s16le 24 kHz mono**: Kokoro's native rate, no resampling, half the size of float32.
- **Last frame**: the last-frame flag is carried by an empty-payload frame sent after the final audio,
  so a segment's tail never waits for the next segment.
- **Concurrency of 1**: one local client at a time; the model is the bottleneck on a 16 GB laptop.
- **Idle timeout** ignores time the server spends applying backpressure to a piece of text.

## Execution provider (T065)
`scripts/eval_providers.py`, 6 reference sentences, voice `ef_dora`:

| Configuration | RTF | Mean WER | Peak RSS | Load |
|---------------|----:|---------:|---------:|-----:|
| fp32, CPU | 0.30 | 0.000 | 623 MB | 1.2 s |
| fp32, Core ML | 0.30 | 0.000 | 1044 MB | 4.6 s |

**Decision**: keep CPU. Core ML is correct on this sample but not faster, uses about 70% more memory
and loads slower.

## Model variant (T070)
| Variant | Size | RTF | Mean WER (6 sentences) | Peak RSS |
|---------|-----:|----:|-----------------------:|---------:|
| fp32 `kokoro-v1.0.onnx` | 326 MB | 0.30 | 0.000 | 623 MB |
| fp16 | 164 MB | 0.32 | 0.000 | 736 MB |
| int8 | 114 MB | 0.15 | 0.000 | 396 MB |

**Decision**: the default stays full precision, because it is the variant that passed the full
12-sentence, 3-voice verification (`verification/voice-verification.json`). int8 is the best
candidate for a smaller/faster option, but must pass `verify-voices` on its own checksum before it is
used. fp16 is unsuitable: slower and larger in memory than fp32 on CPU. No variant is excluded by the
16 GB target; all fit well under the 4 GB ceiling.

## Transports (feature 002)
- **One request per gRPC call** (R-01): `Stream` is bidirectional; cancelling the call is cancelling the
  request, and no request-id multiplexing is needed. `GetCapabilities` is a separate unary call.
- **Errors are in-stream events, call status stays OK** (R-02): terminal outcomes and errors reuse the
  WebSocket codes, categories and `retryable` flag; non-OK status is only for transport faults
  (client cancel/deadline, shutdown, an inbound message over 64 KiB).
- **Generated stubs are committed** (R-11): `src/voxstream/transports/grpc/gen/`, produced by
  `scripts/gen_proto.sh` from `proto/voxstream/v1/voxstream.proto`; a test fails when they are stale,
  and `protobuf` is pinned to a range that includes the version the stubs were generated with.
- **Shared service layer** (R-07): `core/service.py` owns admission, readiness, engine start and request
  opening, so validation and the single concurrency limit are identical across transports; `core` no
  longer imports anything from `transports` (sessions emit a neutral `AudioFrame`, R-08).
- **Health stays on HTTP only** (R-09): `/healthz` and `/readyz` on `VOXSTREAM_PORT` for every mode;
  a minimal listener serves them when WebSocket is disabled. No gRPC health service.
- **Default gRPC port 50051** (R-10), both transports enabled by default, plaintext and local-only.
- **Backpressure**: `grpc.aio` async-generator handlers do apply write backpressure under a stalled
  reader (verified by `tests/integration/test_grpc_backpressure.py`), so no extra credit counter is
  used: a bounded outbox of 8 events plus the existing audio queue pause synthesis.
