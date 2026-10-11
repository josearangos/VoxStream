# Contract: VibeVoice engine adapter and WebSocket behavior

The WebSocket protocol in `specs/001-kokoro-websocket-streaming/contracts/websocket-protocol.md` is
unchanged. This file lists only what is specific to `vibevoice`.

## Selection
- `VOXSTREAM_ENGINE=vibevoice` with `VOXSTREAM_ENABLE_GRPC=false`.
- With gRPC enabled the service refuses to start: `engine 'vibevoice' is not supported on the gRPC
  transport; set VOXSTREAM_ENABLE_GRPC=false.`

## Settings (new, `VOXSTREAM_` prefix)
| Name | Default | Meaning |
|------|---------|---------|
| `vibevoice_model_dir` | `models/vibevoice` | Local model and voice-preset directory |
| `vibevoice_device` | `cpu` | `cpu` or `mps`; an unavailable device is an error, never a silent fallback |

## Adapter obligations (`TTSEngine`)
- `start`: lazy load in a worker thread; missing files or dependencies => `EngineUnavailableError`
  with an actionable message; memory exhaustion => `OutOfMemoryError`.
- `capabilities`: `languages=["es"]`, verified voices only, honest `streaming_mode`.
- `synthesize(text, voice, cancel)`: yields `AudioBlock` int16 mono; checks `cancel` between blocks and
  signals the upstream stop hook; the internal queue is bounded.
- `stop`: releases model and thread; idempotent.

## Errors (existing codes)
| Condition | Code |
|-----------|------|
| Unknown or unverified voice | `UNSUPPORTED_VOICE` |
| No Spanish-verified voice, missing model or dependency | `ENGINE_UNAVAILABLE` |
| Out of memory | `OUT_OF_MEMORY` |
| Non-Spanish language request | existing language rejection |

## Acknowledgement
Reports `engine: "vibevoice"`, the voice used, `pcm_s16le`, the real sample rate, channels 1.
