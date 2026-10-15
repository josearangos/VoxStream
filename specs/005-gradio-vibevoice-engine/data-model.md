# Data Model: VibeVoice in the Gradio demo

In-memory only; nothing persisted.

## ServiceInfo (new, `demo/service_info.py`)
| Field | Meaning |
|-------|---------|
| `reachable` | `/readyz` answered with a parseable body |
| `engine` | Engine name reported by the service (`kokoro`, `vibevoice`) or `None` if unknown |
| `ready` | Service says the engine can synthesize now |
| `reason` | Short not-ready reason (truncated to 200 chars) or `None` |
| `voices` | Voice ids the service offers; empty if unknown |

Derived: `display_name` (Kokoro / VibeVoice / "Unknown"), `other_engines` (known engines minus the
active one), `restart_hint(other)`.

## PlaybackSession (extended, `demo/session.py`)
Adds `engine: str | None` and `voice: str | None`, set from `started` and shown as "Speaking with".
State machine unchanged (see 003 data model). "Preparing speech…" is a status label derived from
`Playing` with no audio received yet, not a state.

## Selection (per browser session)
`voice: str | None` — chosen in the dropdown; `None` means service default (fallback mode).

## Rules
- Voices offered = `ServiceInfo.voices` only (FR-004, FR-009).
- `engine` sent in `start` = `ServiceInfo.engine` when known, else omitted.
- Changing voice or pressing Refresh while active stops the playback first.
