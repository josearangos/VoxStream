# Quickstart: validating the VibeVoice engine

## Prerequisites
- macOS on Apple Silicon, Python 3.12, `uv sync --extra vibevoice --extra verify`.
- Model and Spanish preset voices in `models/vibevoice` (git-ignored):
  `uv run voxstream download-models --engine vibevoice` (about 2 GB, voices `sp-Spk2_woman`,
  `sp-Spk3_man`, `sp-Spk4_woman`, `sp-Spk5_man`).
- `export VOXSTREAM_VIBEVOICE_DEVICE=mps` (the default `cpu` is several times slower).

## 1. Default install is unaffected
`uv sync && uv run pytest` passes without the `vibevoice` extra (SC-006).

## 2. Verify Spanish voices
`uv run voxstream verify-voices --engine vibevoice` (several minutes)
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

## Walkthrough record (2026-10-10, M2 Pro 16 GB)
- Step 1: the default test run (305 passed) uses stubs; the lazy-import tests assert `torch`,
  `transformers` and `vibevoice` are not imported. Not run in a venv without the extra.
- Step 2: ran with `mps`; 2 of 4 voices pass (see README "VibeVoice"). Deviation: the first attempt
  failed because the engine refused to synthesize not-yet-verified candidates; fixed (verification
  builds the engine with unverified voices allowed) and covered by a unit test.
- Step 3: served over WebSocket, only the two verified voices listed in `/readyz`; 8 trials ran.
  Not done: listening to the audio, and the `examples/` client with VibeVoice.
- Step 4: refused with the documented message, exit code 2.
- Step 5: cancel test passes (0 ms); numbers in `docs/measurements.md`. The 2 s first-audio target
  is met warm (195 ms); the first request after load took 2.0 s.
