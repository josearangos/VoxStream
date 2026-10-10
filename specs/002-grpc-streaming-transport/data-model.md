# Data Model: gRPC Streaming Transport

Everything is in memory. Entities reused from 001 are listed by reference; only changes and new
entities are described. See [001 data-model](../001-kokoro-websocket-streaming/data-model.md).

## Audio Frame (`core/frames.py`, new, transport-neutral)

| Field | Description |
|-------|-------------|
| `request_id` | UUID of the request. |
| `sequence` | uint32, starts at 0, +1 per frame, continuous across segments. |
| `last` | True only on the terminator frame (empty payload) sent after the final audio. |
| `pcm` | Signed 16-bit little-endian, mono, 24,000 Hz; at most `frame_ms` of audio. |

Replaces pre-encoded `bytes` passed from `Session` to the transport. WebSocket encodes it with the
21-byte header; gRPC maps it to `AudioChunk`.

## Synthesis Request (unchanged state machine)

States and transitions are identical to 001 (`OPEN`, `ENDING`, `COMPLETED`, `CANCELLED`,
`FAILED`). Transport-specific lifecycle:

```text
gRPC call opened
  --Start--> OPEN --Text*--> OPEN --End--> ENDING --> COMPLETED
  OPEN|ENDING --Cancel event--> CANCELLED (Cancelled event sent)
  OPEN|ENDING --call cancelled or dropped--> CANCELLED (nothing sent)
  OPEN|ENDING --error/timeout/limit--> FAILED (Error event sent)
call ends with status OK after any terminal event
```

One request per call; a second `Start` in the same call yields `BUSY` and does not change state.

## Service (`core/service.py`, new)

| Field | Description |
|-------|-------------|
| `settings` | Shared `Settings`. |
| `engine` | The single `TTSEngine` instance used by all transports. |
| `admission` | One `AdmissionController`; its limit applies across transports. |
| `engine_started` | Lazy-start flag guarded by a lock. |

Operations: `readiness()`, `capabilities()`, and `open_session(engine?, voice?, language?,
send_audio)` which validates engine, language, readiness, voice (default voice rule), acquires an
admission slot, starts the engine if needed, and returns a started `Session` plus its stream
descriptor, or raises a `VoxStreamError` (`UNSUPPORTED_ENGINE`, `UNSUPPORTED_LANGUAGE`,
`ENGINE_UNAVAILABLE`, `UNSUPPORTED_VOICE`, `BUSY`). The caller releases the slot when the session
reaches a terminal state.

## Protocol messages (`proto/voxstream/v1/voxstream.proto`)

Full schema in [contracts/voxstream.proto](contracts/voxstream.proto).

| Message | Direction | Fields |
|---------|-----------|--------|
| `ClientEvent` | client→server | `oneof`: `Start`, `Text`, `End`, `Cancel` |
| `Start` | | `engine?`, `voice?`, `language?` |
| `Text` | | `text`, `request_id?` |
| `End` / `Cancel` | | `request_id?` |
| `ServerEvent` | server→client | `oneof`: `Started`, `AudioChunk`, `Completed`, `Cancelled`, `Error` |
| `Started` | | `request_id`, `StreamDescriptor` |
| `StreamDescriptor` | | `encoding`, `sample_rate`, `channels`, `frame_ms`, `voice`, `engine`, `language`, `streaming_mode`, `execution_provider` |
| `AudioChunk` | | `request_id`, `sequence`, `last`, `pcm` |
| `Completed` | | `request_id`, `audio_frames`, `audio_ms`, `chars`, `timing` |
| `Cancelled` | | `request_id`, `audio_frames_sent` |
| `Error` | | `request_id?`, `code`, `category`, `message`, `retryable` |
| `Capabilities` | unary reply | same fields as the WebSocket capabilities message |

## Settings additions (`config.py`)

| Setting | Default | Validation |
|---------|---------|------------|
| `enable_websocket` | `true` | At least one of the two transports must be enabled. |
| `enable_grpc` | `true` | |
| `grpc_port` | `50051` | 0 allowed (tests, ephemeral); distinct from `port` unless 0. |
