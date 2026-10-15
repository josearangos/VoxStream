# Contract: how the demo uses the service (no service changes)

## Readiness (read-only)
`GET http://<host>:<port>/readyz` — port and host taken from `DEMO_SERVICE_URL`.
Response JSON used: `ready` (bool), `engine` (str), `voices` (list[str]), `reason` (optional str).
HTTP 200 or 503 are both parsed. Timeout 2 s. Any failure → fallback mode (research R7).

## Start message (protocol v1, unchanged schema)
`{"type":"start","engine":"<active engine>","voice":"<selected voice>"}` — both fields optional and
omitted in fallback mode. Errors: `UNSUPPORTED_ENGINE`, `UNSUPPORTED_VOICE`, `ENGINE_UNAVAILABLE`.

## Started message (read)
`stream.engine`, `stream.voice`, `stream.sample_rate`, `stream.channels`, `stream.encoding`
(must be `pcm_s16le`). Engine and voice are displayed verbatim as ids.

## Demo UI contract additions
| Element | Behavior |
|---------|----------|
| Engine radio | Read-only; active engine selected; hint under it for the other engine |
| Voice dropdown | Choices from `voices`; disabled with "Service default" in fallback mode; disabled while playing |
| Refresh button | Re-reads `/readyz`; stops active playback first |
| Info line | `<Engine> · ready` or `<Engine> · not ready: <reason>` |
| Speaking-with line | `Speaking with <engine> · <voice>` once `started` arrives |
| Status | Adds `Preparing speech…` between `started` and the first audio chunk |
