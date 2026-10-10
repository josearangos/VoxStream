# Data Model: Kokoro Spanish TTS Streaming over WebSocket

All entities are in-memory except the verification result, which is a JSON file. Field types are
logical; the Python models live in `src/voxstream/`.

## Synthesis Request (`core/session.py`)

| Field | Description / validation |
|-------|-------------------------|
| `request_id` | UUID assigned by the server at `start`; carried on every message. |
| `engine` | Optional requested engine name; must exist in the registry, else `UNSUPPORTED_ENGINE`. |
| `voice` | Optional; must be in the engine's verified Spanish voices, else `UNSUPPORTED_VOICE`. Default: first verified voice from config. |
| `language` | Optional; must be `es`, else `UNSUPPORTED_LANGUAGE`. Default `es`. |
| `chars_received` | Running total; must not exceed `max_text_chars` (default 2000), else `TEXT_TOO_LONG`. |
| `state` | See state machine below. |
| `timing` | Per-request timing record (below). |

### State machine

```text
(connected) --start--> OPEN --text--> OPEN
OPEN --end--> ENDING --all audio sent--> COMPLETED
OPEN|ENDING --cancel or disconnect--> CANCELLED
OPEN|ENDING --error, idle timeout, request timeout, limit--> FAILED
```

`COMPLETED`, `CANCELLED` and `FAILED` are terminal. Exactly one terminal message is sent per
request, and the admission slot is released on every transition into a terminal state. After a
terminal state the connection may open a new request.

## Text Piece (`transports/websocket/messages.py`)

| Field | Description / validation |
|-------|-------------------------|
| `request_id` | Must match the active request, else `NO_ACTIVE_REQUEST` / `REQUEST_MISMATCH`. |
| `text` | String; empty or whitespace-only pieces are accepted and ignored; contributes to `chars_received`. |

The end-of-text signal is a separate `end` message with the same `request_id`.

## Text Segment (`core/segmenter.py`)

| Field | Description |
|-------|-------------|
| `index` | Zero-based order within the request. |
| `text` | Speakable unit passed to the engine. |
| `reason` | `sentence_end`, `fallback_length`, or `end_of_text`. |

Rules: segments are emitted strictly in text order; the concatenation of all segment texts equals
the received text with whitespace normalized.

## Audio Block and Audio Frame (`engines/base.py`, `framing.py`)

- **Audio block** (engine output): `samples` (PCM int16 array), `sample_rate`, `channels`.
- **Audio frame** (wire): request id, sequence number (continuous across segments, starting at 0),
  flags (bit 0 = last frame), payload (default 100 ms of PCM s16le, last frame of a segment may be
  shorter).

## Stream Descriptor

| Field | Description |
|-------|-------------|
| `encoding` | `pcm_s16le`. |
| `sample_rate` | 24000. |
| `channels` | 1. |
| `frame_ms` | Nominal frame duration (100). |
| `voice`, `engine`, `language` | Values actually used. |
| `streaming_mode` | `incremental`, `segmented` or `complete_then_chunked`; Kokoro reports `segmented`. |
| `execution_provider` | Provider actually in use (e.g. `CPUExecutionProvider`). |

## Control Messages and Error

Defined in [contracts/websocket-protocol.md](contracts/websocket-protocol.md). Error fields:
`request_id` (nullable), `code` (stable), `category` (`validation`, `capacity`, `engine`,
`timeout`, `protocol`, `internal`), `message` (actionable, no internal paths or traces),
`retryable` (boolean).

## Engine Capabilities (`engines/base.py`)

| Field | Description |
|-------|-------------|
| `name`, `version` | Engine and model identity (model checksum for Kokoro). |
| `languages` | Supported language codes (`["es"]` here). |
| `voices` | Verified voices exposed to clients. |
| `audio_format` | Encoding, sample rate, channels. |
| `streaming_mode` | As above. |
| `supports_cancel` | Whether synthesis can be interrupted and at what granularity. |
| `execution_provider` | Runtime provider in use. |
| `memory_notes` | Short description of observed memory use (documented, not enforced). |

## Request Timing Record (`core/metrics.py`)

| Field | Description |
|-------|-------------|
| `t_start` | Request opened. |
| `t_first_text` | First non-empty text piece. |
| `t_first_segment` | First segment completed by the segmenter. |
| `t_first_audio_generated` | Engine produced first samples. |
| `t_first_audio_sent` | First audio frame written to the socket. |
| `segments[]` | Per segment: characters, synthesis ms, audio ms. |
| `t_end` | Terminal message sent. |
| derived | `ttfa_from_first_segment_ms`, `generation_ms`, `delivery_ms`, `rtf`. |

Generation time and delivery time are recorded separately (FR-024).

## Voice Verification Result (`verification/voice-verification.json`)

```text
{
  "model": {"name": "kokoro-v1.0", "sha256": "..."},
  "recognizer": {"name": "faster-whisper small", "language": "es"},
  "threshold": {"mean_wer": 0.15, "max_sentence_wer": 0.35},
  "voices": {
    "<voice>": {
      "mean_wer": 0.0, "max_sentence_wer": 0.0, "passed": true,
      "sentences": [{"reference": "...", "transcript": "...", "wer": 0.0}],
      "manual_signoff": {"by": "...", "date": "YYYY-MM-DD"} | null
    }
  },
  "generated_at": "YYYY-MM-DDTHH:MM:SSZ"
}
```

Validation: a voice is exposed only if `passed` is true and `model.sha256` matches the installed
model file; otherwise it is hidden and requests for it get `UNSUPPORTED_VOICE`. If no voice is
exposed the service is not ready (`/readyz` returns 503 with the reason).
