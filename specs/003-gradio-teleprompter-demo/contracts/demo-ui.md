# Contract: Demo UI and Service Usage

## Service usage (no changes to protocol v1)
The demo uses only messages from `specs/001-kokoro-websocket-streaming/contracts/websocket-protocol.md`:

1. Connect to `DEMO_SERVICE_URL`; send `{"type":"start"}` (default Spanish voice).
2. On `started`: read `stream` (encoding `pcm_s16le`, `sample_rate`, `channels`); abort with a
   message if the encoding is anything else.
3. Send one `text` message with the full text, then `end`.
4. Relay each binary frame payload (bytes after the 21-byte header) to the audio output; ignore a
   final empty payload.
5. On `completed`: record `audio_ms`, rescale the timeline, finish. On `error`/`cancelled`: show
   message, end.
6. Stop or page disconnect: send `cancel` with the `request_id`, then close.

## UI elements
| Element | Behavior |
|---------|----------|
| Text box (multi-line) | Spanish text; pre-filled with a sample Spanish paragraph |
| Start button | Disabled while a session is active; validates text first |
| Stop button | Enabled only while a session is active |
| Status line | One of: Ready, Connecting, Playing, Finished, Stopped, Error: <message> |
| Audio output | Streaming, autoplay, no upload/record controls |
| Teleprompter panel | Words shown as spoken (dimmed), current (highlighted), upcoming (normal); auto-scrolls to keep the current word visible |

## Message table (plain language)
| Condition | Message (UI text) |
|-----------|-------------------------------------------|
| Empty input | "Enter some text first." |
| Cannot connect / dropped | "Can't reach the VoxStream service at <url>. Is it running?" |
| `BUSY` | "The service is busy with another request. Try again in a moment." |
| `TEXT_TOO_LONG` / pre-check | "Text is too long (max <n> characters)." |
| Other service error | "The service reported an error (<code>). Try again." |
| Autoplay blocked | "Your browser blocked audio. Click the player's play button." |
