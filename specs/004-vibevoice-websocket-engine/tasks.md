---

description: "Task list for the Microsoft VibeVoice Spanish engine (WebSocket)"
---

# Tasks: Microsoft VibeVoice Spanish Engine (WebSocket)

**Input**: Design documents from `/specs/004-vibevoice-websocket-engine/`

**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/engine-vibevoice.md, quickstart.md

**Tests**: Included. The constitution (IX) requires unit and integration coverage for engine adapters, errors and cancellation; model-loading tests are marked `model` and excluded by default.

**Organization**: Grouped by user story. Paths are relative to the repository root.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependency on unfinished tasks)
- **[Story]**: US1, US2, US3 from spec.md

---

## Phase 1: Setup and Compatibility Spike

**Purpose**: Resolve the unknowns from research.md (R-03, R-04, R-08) before any adapter code. If no working Apple Silicon path exists, stop and document it (constitution VII).

- [ ] T001 Add optional extra `vibevoice` (torch, transformers, upstream `vibevoice` package, pinned versions) to `pyproject.toml` and add `models/vibevoice/` to `.gitignore`; add `vibevoice.*`, `torch.*`, `transformers.*` to the mypy `ignore_missing_imports` override
- [ ] T002 Run a throwaway spike script in the scratchpad (not committed) that loads `microsoft/VibeVoice-Realtime-0.5B` on CPU then MPS on this Mac, generates a Spanish sentence with each downloaded Spanish preset, and records: working device, peak memory, sample rate, streaming API and stop hook names (read upstream `demo/vibevoice_realtime_demo.py`), Spanish preset file names (run upstream `demo/download_experimental_voices.sh`)
- [ ] T003 Write the spike outcome into `specs/004-vibevoice-websocket-engine/research.md` as new section "R-09 Spike results" (device, API names, voice names, sample rate, memory, go/no-go); if no-go, document it in `docs/measurements.md` and stop here

**Checkpoint**: Go decision recorded; API names and voice names known.

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Make settings, registry, voice gate and verification engine-aware without changing Kokoro behavior.

- [ ] T004 [P] Move the voice gate (`VoiceGate`, `load_gate`) from `src/voxstream/engines/kokoro/voices.py` into new `src/voxstream/engines/voice_gate.py`; keep `CANDIDATE_VOICES` and `LANGUAGE` in the Kokoro module and re-import the gate there; keep `tests/unit/test_voice_gate.py` passing
- [ ] T005 [P] Add settings `vibevoice_model_dir: str = "models/vibevoice"` and `vibevoice_device: str = "cpu"` to `src/voxstream/config.py`
- [ ] T005a Derive the verification result path from the engine name in `src/voxstream/config.py` (`verification/vibevoice-verification.json` for vibevoice; keep `verification/voice-verification.json` for kokoro) and use it in T008, T019 and T024
- [ ] T006 Add `ENGINE_TRANSPORTS` mapping (`kokoro` and `mock`: websocket+grpc; `vibevoice`: websocket) and `"vibevoice"` in `KNOWN_ENGINES` with lazy import in `src/voxstream/engines/registry.py`
- [ ] T007 Extend `Settings.validate_transports` in `src/voxstream/config.py` to raise `engine 'vibevoice' is not supported on the gRPC transport; set VOXSTREAM_ENABLE_GRPC=false.` when the engine does not support an enabled transport (uses `ENGINE_TRANSPORTS`)
- [ ] T008 [P] Make `src/voxstream/verification/spanish.py` engine-parameterized: result file path `verification/<engine>-verification.json` (keep `verification/voice-verification.json` for Kokoro), model name/sha supplied by the engine, synthesis callback unchanged
- [ ] T009 Add `--engine` (default from settings) to the `verify-voices` command in `src/voxstream/cli.py` and route to the matching engine's candidates
- [ ] T010 [P] Unit tests in `tests/unit/test_registry.py` and `tests/unit/test_config_errors.py`: `vibevoice` is a known engine; `engine=vibevoice` with gRPC enabled raises the exact error from T007; `engine=vibevoice` with gRPC disabled passes
- [ ] T011 [P] Add `tests/integration/test_lazy_transport_imports.py` case asserting that importing `voxstream`, the registry and the app does not import `torch`, `transformers` or `vibevoice`
- [ ] T011a Parametrize the shared contract tests in `tests/contract/` over a stub `vibevoice` engine so the engine passes them before being called supported (constitution Governance)

**Checkpoint**: Kokoro and mock behave exactly as before; `uv run pytest` is green without the `vibevoice` extra.

---

## Phase 3: User Story 1 - Stream Spanish speech from VibeVoice over WebSocket (Priority: P1) 🎯 MVP

**Goal**: With `VOXSTREAM_ENGINE=vibevoice`, an unmodified WebSocket client gets ordered Spanish audio and a completion message.

**Independent Test**: Quickstart step 3 with a Spanish paragraph; plus stub-engine tests below that run without the model.

### Tests for User Story 1

- [ ] T012 [US1] Contract tests for the adapter in `tests/unit/test_vibevoice_engine.py` using a fake model object injected into the adapter: yields int16 mono `AudioBlock`s, `capabilities()` returns languages `["es"]` and only verified voices, `stop()` is idempotent, queue is bounded
- [ ] T013 [US1] Error mapping tests in `tests/unit/test_vibevoice_engine.py`: missing model dir => `EngineUnavailableError` mentioning the download step; `MemoryError` => `OutOfMemoryError`; unverified voice => unsupported-voice error; no verified voice => `EngineUnavailableError` stating no Spanish-verified voice is available (FR-007a)
- [ ] T014 [P] [US1] Cancel test in `tests/unit/test_vibevoice_engine.py`: setting `CancelToken` stops block production and calls the (fake) upstream stop hook
- [ ] T015 [US1] WebSocket flow test in `tests/integration/test_ws_streaming.py` (new parametrized case) running the real server with a stub `vibevoice`-named engine: acknowledgement reports `engine: "vibevoice"`, voice, `pcm_s16le`, sample rate; binary frames ordered; completion message sent
- [ ] T015a [US1] Extend the T015 test to run the same Spanish text through stub `kokoro` and `vibevoice` engines and assert the message sequence and frame headers are identical except for the reported engine and voice (SC-001)
- [ ] T015b [US1] Add a default-voice case in `tests/integration/test_ws_streaming.py`: a request without a voice uses the first verified voice and the acknowledgement names it; an unknown voice gets `UNSUPPORTED_VOICE` and no audio
- [ ] T015c [US1] Add `vibevoice` to the stub engine parametrization in `tests/integration/test_disconnect.py` so a client disconnect stops generation (FR-008)

### Implementation for User Story 1

- [ ] T016 [P] [US1] Create `src/voxstream/engines/vibevoice/__init__.py` and `src/voxstream/engines/vibevoice/voices.py` with `CANDIDATE_VOICES` (Spanish preset names found in T002) and `LANGUAGE = "es"`
- [ ] T017 [US1] Implement `VibeVoiceEngine` in `src/voxstream/engines/vibevoice/engine.py`: lazy idempotent `start()` loading in a worker thread from `settings.vibevoice_model_dir` on `settings.vibevoice_device` (unavailable device => error, no silent fallback); `capabilities()` with honest `streaming_mode`, device actually used, memory notes that state "WebSocket only"; model checksum for the gate; module docstring declaring init/inference/cancel/shutdown like the Kokoro adapter
- [ ] T018 [US1] Implement `synthesize()` in `src/voxstream/engines/vibevoice/engine.py`: generation in a worker thread feeding a bounded `asyncio.Queue`; convert float audio to int16 clipped to ±32767; check `cancel` between blocks and call the upstream stop hook; map `MemoryError`/allocation errors to `OutOfMemoryError`, other failures to `EngineError` without logging text
- [ ] T019 [US1] Implement `stop()` and gate usage in `src/voxstream/engines/vibevoice/engine.py`: release model and thread deterministically; `gate()`/`readiness()` use `src/voxstream/engines/voice_gate.py` with `settings.verification_file` equivalent for `verification/vibevoice-verification.json`; refuse synthesis when the gate has no voices
- [ ] T019a [US1] Resolve the default voice in `src/voxstream/engines/vibevoice/engine.py` and the service: `VOXSTREAM_DEFAULT_VOICE` if set and verified, else the first verified voice; the acknowledgement reports the voice used (FR-005, acceptance scenario 2)
- [ ] T020 [US1] Add `download-models --engine vibevoice` support in `src/voxstream/cli.py` (fetch model and Spanish preset files from the documented upstream sources into `models/vibevoice`, printing source URLs)
- [ ] T021 [US1] Mark a real-model test in `tests/integration/test_vibevoice_real.py` with `@pytest.mark.model`: streams one Spanish sentence, first chunk arrives, completion received (excluded by default)

**Checkpoint**: US1 works end to end with the stub in CI and with the real model locally.

---

## Phase 4: User Story 2 - Verify the VibeVoice voices speak Spanish (Priority: P2)

**Goal**: Each preset voice gets a pass/fail result; only passing voices are exposed.

**Independent Test**: Quickstart step 2; unit tests with a fake recognizer.

### Tests for User Story 2

- [ ] T022 [P] [US2] Unit tests in `tests/unit/test_voice_gate.py` for the vibevoice file: stale checksum => no voices; all failed => no voices and reason "No Spanish voice passed verification"; one passed => exposed with sign-off warning
- [ ] T023 [P] [US2] Unit test in `tests/unit/test_verification.py` that verification with `engine="vibevoice"` writes `verification/vibevoice-verification.json` and leaves the Kokoro file untouched

### Implementation for User Story 2

- [ ] T024 [US2] Wire `VibeVoiceEngine` into the verification flow in `src/voxstream/verification/spanish.py` and `src/voxstream/cli.py` (synthesis callback resamples to 24 kHz mono if the engine rate differs; uses `verification/reference_sentences_es.txt` and the thresholds `verify_mean_wer` / `verify_max_sentence_wer`)
- [ ] T025 [US2] Add `--signoff <voice>` support for vibevoice results in `src/voxstream/cli.py` (reuses the existing manual sign-off recording)
- [ ] T026 [US2] Run `uv run voxstream verify-voices --engine vibevoice` locally and commit the resulting `verification/vibevoice-verification.json` (pass or fail); document the outcome in `README.md` under a new "VibeVoice" section

**Checkpoint**: Voice list is gated by evidence; zero passing voices => engine refuses with a structured error.

---

## Phase 5: User Story 3 - Compare VibeVoice against Kokoro with measurements (Priority: P3)

**Goal**: Comparable latency, memory and cancel numbers for both engines.

**Independent Test**: Quickstart step 5.

- [ ] T027 [P] [US3] Parametrize the cancel-latency test in `tests/integration/test_cancel_latency.py` by engine so a `model`-marked VibeVoice case measures stop time after a cancel message
- [ ] T028 [US3] Run the existing measurement procedure from `docs/measurements.md` for `vibevoice` (cold and warm TTFA, inter-chunk delay, RTF, peak memory, cancel latency; repeated trials with median and p95) and add rows beside Kokoro, recording device, versions and whether the 2 s TTFA target (SC-003) was met
- [ ] T029 [US3] Add the engine comparison procedure (one documented command sequence for both engines) to `docs/measurements.md` (SC-005)

**Checkpoint**: Both engines have comparable, reproducible results.

---

## Phase 6: Polish and Cross-Cutting

- [ ] T030 [P] Document VibeVoice in `README.md`: install (`uv sync --extra vibevoice`), model download, WebSocket-only limitation and error text, Spanish experimental status, supported voices, memory, streaming mode (constitution XIII)
- [ ] T031 [P] Update `specs/004-vibevoice-websocket-engine/quickstart.md` with the exact commands and voice names found in the spike
- [ ] T032 Run `uv run ruff check`, `uv run mypy` and `uv run pytest` (including `tests/contract`) without the extra; fix findings (SC-006)
- [ ] T033 Walk through every step of `specs/004-vibevoice-websocket-engine/quickstart.md` and record any deviations

---

## Dependencies and Execution Order

- Phase 1 (spike) blocks everything; a no-go decision ends the feature with documentation.
- Phase 2 blocks all user stories. T004 before T008 and T019; T006 before T007 and T010.
- US1 (Phase 3) is the MVP. US2 depends on the engine from US1 (T017–T019). US3 depends on US1 and benefits from US2 (verified voices to measure).
- Within US1: tests (T012–T015) before implementation; T016 before T017; T017 before T018 and T019.

## Parallel Opportunities

- Phase 2: T004, T005, T008, T011 touch different files and can run together; T010 after T006/T007.
- US1: T012, T013, T014 (same file, write together) and T016 in parallel with T015.
- US2: T022 and T023 in parallel.
- Polish: T030 and T031 in parallel.

## Implementation Strategy

1. Spike (Phase 1) and decide go/no-go.
2. Foundational (Phase 2), keeping Kokoro tests green.
3. US1 MVP with the stub; validate with the real model.
4. US2 verification gate (required before calling the engine supported).
5. US3 measurements, then polish.
