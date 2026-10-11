# Quickstart: validating the VibeVoice engine

## Prerequisites
- macOS on Apple Silicon, Python 3.12, `uv sync --extra vibevoice --extra verify`.
- Model and Spanish preset voices placed in `models/vibevoice` (download steps are documented in the
  README by this feature; files are not committed).

## 1. Default install is unaffected
`uv sync && uv run pytest` passes without the `vibevoice` extra (SC-006).

## 2. Verify Spanish voices
`uv run voxstream verify-voices --engine vibevoice`
Expect `verification/vibevoice-verification.json` with a pass/fail per voice. If none pass, step 3
must return `ENGINE_UNAVAILABLE`.

## 3. Stream over WebSocket
`VOXSTREAM_ENGINE=vibevoice VOXSTREAM_ENABLE_GRPC=false uv run voxstream serve`
Use the existing example client with Spanish text. Expect an acknowledgement naming `vibevoice`, ordered
binary audio frames, then a completion message (User Story 1).

## 4. gRPC guard
Start with `VOXSTREAM_ENABLE_GRPC=true`; expect the "not supported on the gRPC transport" error.

## 5. Cancel and measure
Run the cancel test and the measurement suite with `--engine vibevoice`; record results beside Kokoro
in `docs/measurements.md` (TTFA target 2 s, SC-003).
