# Contract: gRPC Streaming Protocol (v1)

Endpoint: `127.0.0.1:50051` (plaintext, local only; host and `VOXSTREAM_GRPC_PORT` configurable).
Service `voxstream.v1.Synthesizer`; schema in [voxstream.proto](../proto/voxstream/v1/voxstream.proto).
Health: the existing HTTP `GET /healthz` and `GET /readyz` on the WebSocket port (or the
standalone listener on the same port when WebSocket is disabled). There is no gRPC health service.

## Calls

| RPC | Shape | Purpose |
|-----|-------|---------|
| `Stream` | bidirectional streaming | One synthesis request per call. |
| `GetCapabilities` | unary | Engine capabilities; allowed at any time. |

## Message mapping (WebSocket ↔ gRPC)

| WebSocket | gRPC | Notes |
|-----------|------|-------|
| `start` | `ClientEvent.start` | First event of the call. |
| `text` | `ClientEvent.text` | `request_id` optional; the call scopes the request. |
| `end` | `ClientEvent.end` | |
| `cancel` | `ClientEvent.cancel` | Also: cancelling or dropping the call. |
| `capabilities` | `GetCapabilities` | Separate unary call; no "no active request" restriction. |
| `started` | `ServerEvent.started` | Same fields. |
| binary audio frame | `ServerEvent.audio` (`AudioChunk`) | Same fields; protobuf replaces the 21-byte header. |
| `completed` | `ServerEvent.completed` | Same fields. |
| `cancelled` | `ServerEvent.cancelled` | Same fields. |
| `error` | `ServerEvent.error` | Same `code`, `category`, `message`, `retryable`. |

Audio is the same: `pcm_s16le`, 24,000 Hz, mono, ≤ `frame_ms` per chunk. Audio chunks are
distinguishable from control events by the `oneof` case.

## Call lifecycle

1. Client opens `Stream` and sends `Start`.
2. Server replies `Started` (request id and stream descriptor) or `Error` (rejected `Start`).
3. Client sends `Text` events, then `End`. Audio chunks arrive while text is still being sent.
4. Server sends exactly one terminal event (`Completed`, `Cancelled` or `Error` for the active
   request) and then ends the call with gRPC status `OK`.
5. A rejected `Start` is followed by call end with status `OK` (one request per call).

Non-`OK` status only occurs for transport faults: client-side cancel/deadline, server shutdown, or an oversize message (> 64 KiB), which fails the call with `RESOURCE_EXHAUSTED` just as WebSocket closes the connection with code 1009. Oversize is a transport fault on both transports, not an application error, and the admission slot is released.

## Error codes

Identical to the WebSocket table in
[websocket-protocol.md](../specs/001-kokoro-websocket-streaming/contracts/websocket-protocol.md).
Every code is delivered as `ServerEvent.error` with the same `code`, `category`, `message` and
`retryable`; `request_id` is unset for a rejected `Start`.

| Code | Category | gRPC behavior | Ends the request? |
|------|----------|---------------|-------------------|
| `MALFORMED_MESSAGE` | protocol | A `ClientEvent` with no case set; the call stays open. (Invalid JSON and client binary frames do not exist in gRPC.) | No |
| `NO_ACTIVE_REQUEST` | protocol | `Text`/`End`/`Cancel` before `Start`, or `Text` after `End` (request continues). | No |
| `REQUEST_MISMATCH` | protocol | `request_id` present and different from the active request. | No |
| `BUSY` | capacity | Service at its limit (any transport), or a second `Start` in the same call (first request unaffected). | Rejected `Start`: call ends `OK` |
| `UNSUPPORTED_LANGUAGE` | validation | `Start.language` other than `es`. | `Start` rejected, call ends `OK` |
| `UNSUPPORTED_VOICE` | validation | `Start.voice` not verified; message lists available voices. | `Start` rejected, call ends `OK` |
| `UNSUPPORTED_ENGINE` | validation | `Start.engine` unknown or not the configured engine. | `Start` rejected, call ends `OK` |
| `TEXT_TOO_LONG` | validation | Total text exceeds `max_text_chars`. | Yes |
| `EMPTY_REQUEST` | validation | `End` with no text at all. | Yes |
| `IDLE_TIMEOUT` | timeout | No text or `End` within the idle timeout; pending complete segments are spoken first. | Yes |
| `REQUEST_TIMEOUT` | timeout | Request exceeds the maximum duration. | Yes |
| `ENGINE_FAILURE` | engine | Engine raised during synthesis. | Yes |
| `ENGINE_UNAVAILABLE` | engine | Model missing or failed to load; no verified voice. | `Start` rejected, call ends `OK` |
| `OUT_OF_MEMORY` | engine | Memory exhaustion while synthesizing. | Yes |
| `INTERNAL_ERROR` | internal | Anything unexpected; message is generic. | Yes |

A half-closed request stream (client done writing) without `End` is not an `End`: the idle timeout
applies. A client that sends `End` may half-close and keep reading until the terminal event.

## Rules

1. Exactly one terminal event per accepted request. Rejected `Start` gets an `Error` with no
   `request_id` and no other terminal event.
2. After `Cancel`, audio stops, further `Text`/`End` are ignored, and `Cancelled` is sent. A cancel
   racing with completion yields `Completed` or `Cancelled`, never both.
3. If the client cancels or drops the call, the server cancels generation and releases the request
   and its admission slot without sending an event.
4. `End` flushes remaining text even without sentence punctuation; `Completed` follows the last
   audio chunk.
5. Backpressure: the server stops reading inbound events when its text buffer is full and pauses
   synthesis when the outbound audio buffer is full (HTTP/2 flow control reaches the client).
6. Chunks for a request arrive in sequence order with no gaps; no chunk follows a terminal event.
7. The concurrency limit is service-wide across WebSocket and gRPC.

## Contract test obligations (run for both transports, mock engine and Kokoro)

Ordered continuous sequence numbers; first audio before `End` when a sentence completed; exactly
one terminal event; cancel stops audio and yields `Cancelled`; disconnect/call drop releases the
slot; every error code reproduced; unsupported language/voice rejected; second `Start` rejected as
`BUSY`; limit crossing yields `TEXT_TOO_LONG`; identical audio bytes for the same text, voice and
engine across transports; cross-transport `BUSY` while the other transport holds the slot.
