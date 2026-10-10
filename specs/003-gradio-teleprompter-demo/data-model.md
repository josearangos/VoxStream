# Data Model: Gradio Teleprompter Demo

All entities are in-memory and per session; nothing is persisted (FR-011).

## Playback Session
| Field | Description |
|-------|-------------|
| `state` | `ready`, `connecting`, `playing`, `finished`, `stopped`, `error` |
| `text` | Submitted text (not logged) |
| `request_id` | Id from the service `started` message; absent before then |
| `audio_ms_received` | Running total of audio duration relayed to the browser |
| `total_audio_ms` | Set from the `completed` message; absent until then |
| `error` | Plain-language message, set when `state` is `error` |

Transitions: `ready → connecting → playing → finished`; `playing|connecting → stopped` (Stop);
any active state `→ error` (unreachable, busy, over-length, service error, dropped connection);
`finished|stopped|error → ready` on the next Start (or immediately for Stop/error).
Only one non-`ready` session exists at a time; Start while active stops the active one first.

## Word Timeline
Ordered list of **Timeline Words**: `index`, `text`, `char_start`, `char_end`, `weight`,
`start_s`, `end_s`. Built once from the text; `rescale(total_audio_s)` multiplies all times by one
factor. `word_at(seconds)` returns the index of the word being spoken (clamped to first/last).

## Teleprompter Position
`current_index` (word being spoken), derived from the Word Timeline and the playback signal.
Words with index below it are *spoken*, at it *current*, above it *upcoming*; at `finished` all
words are spoken.

## Validation rules
- Text is empty after trimming → rejected before connecting (FR-007).
- Text longer than the configured limit → rejected before connecting with the limit shown (FR-008).
