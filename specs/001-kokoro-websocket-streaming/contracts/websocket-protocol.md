# Contract: WebSocket Streaming Protocol (v1)

Endpoint: `ws://127.0.0.1:8765/v1/stream` (host and port configurable; localhost by default).
Health: `GET /healthz` (process alive, 200) and `GET /readyz` (200 when a verified Spanish voice
and the engine are available, otherwise 503 with a JSON reason and the execution provider).

Frames: **control messages are JSON text frames; audio is binary frames.** A receiver tells them
apart by frame type alone.

One active request per connection and, by default, one active request service-wide.

## Client → server (JSON text frames)

| `type` | Fields | Notes |
|--------|--------|-------|
| `start` | `engine?`, `voice?`, `language?` | Opens a request. Language, if given, must be `es`. |
| `text` | `request_id`, `text` | A piece of text; may split words or sentences. |
| `end` | `request_id` | No more text will be sent. |
| `cancel` | `request_id` | Stop generation and delivery. |
| `capabilities` | none | Ask for engine capabilities; allowed when no request is active. |

## Server → client (JSON text frames)

| `type` | Fields | Meaning |
|--------|--------|---------|
| `started` | `request_id`, `stream` (Stream Descriptor) | Request accepted; client may send text. |
| `capabilities` | Engine Capabilities | Reply to `capabilities`. |
| `completed` | `request_id`, `audio_frames`, `audio_ms`, `chars`, `timing` | Terminal: all audio delivered after `end`. |
| `cancelled` | `request_id`, `audio_frames_sent` | Terminal: stopped at client request or disconnect. |
| `error` | `request_id` (nullable), `code`, `category`, `message`, `retryable` | Failure; terminal for a request if it carries a `request_id` of an active request. |

Example exchange:

```text
C: {"type":"start","voice":"ef_dora"}
S: {"type":"started","request_id":"6f1c...","stream":{"encoding":"pcm_s16le","sample_rate":24000,"channels":1,"frame_ms":100,"voice":"ef_dora","engine":"kokoro","language":"es","streaming_mode":"segmented","execution_provider":"CPUExecutionProvider"}}
C: {"type":"text","request_id":"6f1c...","text":"Hola, "}
C: {"type":"text","request_id":"6f1c...","text":"¿cómo estás hoy? Me alegra verte."}
S: <binary audio frame seq 0>
S: <binary audio frame seq 1> ...
C: {"type":"end","request_id":"6f1c..."}
S: <remaining binary frames>
S: {"type":"completed","request_id":"6f1c...","audio_frames":57,"audio_ms":5600,"chars":38,"timing":{...}}
```

## Binary audio frame

```text
offset  size  field
0       16    request_id (UUID, big-endian bytes)
16      4     sequence number (uint32, big-endian, starts at 0, +1 per frame, continuous across segments)
20      1     flags: bit 0 = last audio frame of the request; other bits reserved (0)
21      N     PCM payload: signed 16-bit little-endian, mono, 24000 Hz (per `stream` descriptor)
```

Guarantees: frames for a request arrive in sequence order with no gaps; no audio frame follows a
terminal message; the descriptor in `started` is sufficient to decode every frame.

## Error codes

| Code | Category | When | Request ends? | `retryable` |
|------|----------|------|---------------|-------------|
| `MALFORMED_MESSAGE` | protocol | Invalid JSON, unknown `type`, missing field. | No (connection kept) | false |
| `NO_ACTIVE_REQUEST` | protocol | `text`, `end` or `cancel` without an open request. | No | false |
| `REQUEST_MISMATCH` | protocol | `request_id` does not match the active request. | No | false |
| `BUSY` | capacity | `start` while this connection or the service is at its limit. | No (active stream unaffected) | true |
| `UNSUPPORTED_LANGUAGE` | validation | Language other than `es`. | `start` rejected | false |
| `UNSUPPORTED_VOICE` | validation | Voice not in the verified list; message lists available voices. | `start` rejected | false |
| `UNSUPPORTED_ENGINE` | validation | Unknown engine, or not the configured engine. | `start` rejected | false |
| `TEXT_TOO_LONG` | validation | Total text exceeds `max_text_chars`. | Yes (failed) | false |
| `EMPTY_REQUEST` | validation | `end` received with no text at all. | Yes (failed) | false |
| `IDLE_TIMEOUT` | timeout | No text or `end` within the idle timeout. | Yes (pending complete segments are spoken first) | true |
| `REQUEST_TIMEOUT` | timeout | Request exceeds the maximum duration. | Yes | true |
| `ENGINE_FAILURE` | engine | Engine raised during synthesis. | Yes | false |
| `ENGINE_UNAVAILABLE` | engine | Model missing or failed to load; no verified voice. | `start` rejected | false |
| `OUT_OF_MEMORY` | engine | Memory exhaustion while synthesizing. | Yes | false |
| `INTERNAL_ERROR` | internal | Anything unexpected; message is generic. | Yes | false |

Messages never contain stack traces, file paths or the input text.

## Rules

1. Exactly one terminal message (`completed`, `cancelled`, or `error` for the active request) per
   request. Rejected `start` requests get an `error` with `request_id: null`.
2. After `cancel`, the server stops sending audio, ignores further `text`/`end` for that
   request, and sends `cancelled`. A `cancel` that races with completion yields either
   `completed` or `cancelled`, never both.
3. On disconnect the server cancels the request and releases resources without sending.
4. `end` flushes remaining text even without a sentence ending, then `completed` follows the last
   audio frame.
5. Backpressure: the server stops reading from the socket when its text buffer is full and pauses
   synthesis when the audio buffer is full.
6. A `text` message received after `end` (request in `ENDING`) is answered with
   `NO_ACTIVE_REQUEST`; the request continues to completion.

## Contract test obligations (run against mock engine and Kokoro)

Ordered continuous sequence numbers; first frame before `end` when a sentence completed; exactly
one terminal message; cancel stops frames and yields `cancelled`; disconnect releases the slot;
each error code above reproduced; unsupported language/voice rejected; second `start` rejected as
`BUSY`; limit crossing yields `TEXT_TOO_LONG`.
