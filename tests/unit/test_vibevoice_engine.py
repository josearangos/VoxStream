import asyncio
import json

import numpy as np
import pytest

from helpers import FakeVibeBackend, make_settings
from voxstream.engines.base import (
    CancelToken,
    EngineError,
    EngineUnavailableError,
    OutOfMemoryError,
)
from voxstream.engines.vibevoice.engine import QUEUE_BLOCKS, VibeVoiceEngine
from voxstream.engines.vibevoice.voices import CANDIDATE_VOICES

VOICE = CANDIDATE_VOICES[0]


def engine(backend=None, **settings):
    settings.setdefault("allow_unverified_voices", True)
    return VibeVoiceEngine(make_settings(engine="vibevoice", **settings), backend=backend)


async def collect(eng, text="Hola mundo", voice=VOICE, cancel=None):
    return [b async for b in eng.synthesize(text, voice, cancel or CancelToken())]


async def test_yields_int16_mono_blocks():
    backend = FakeVibeBackend()
    eng = engine(backend)
    blocks = await collect(eng)
    assert backend.loaded and blocks
    assert all(b.samples.dtype == np.int16 and b.channels == 1 for b in blocks)
    assert all(b.sample_rate == 24000 for b in blocks)
    assert max(int(np.abs(b.samples).max()) for b in blocks) <= 32767
    await eng.stop()


async def test_float_audio_is_clipped_not_wrapped():
    class Loud(FakeVibeBackend):
        def stream(self, text, voice, should_stop):
            yield np.array([5.0, -5.0, 0.5], dtype=np.float32)

    blocks = await collect(engine(Loud()))
    assert list(blocks[0].samples) == [32767, -32767, 16383]


async def test_capabilities_are_spanish_and_gated():
    caps = engine(FakeVibeBackend()).capabilities()
    assert caps.name == "vibevoice" and caps.languages == ["es"]
    assert caps.voices == list(CANDIDATE_VOICES)
    assert caps.streaming_mode == "incremental"
    assert "WebSocket only" in caps.memory_notes
    only_verified = engine(FakeVibeBackend(), allow_unverified_voices=False)
    assert only_verified.capabilities().voices == []  # no verification file => nothing exposed


async def test_gate_exposes_only_passed_voices(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "verification").mkdir()
    (tmp_path / "verification" / "vibevoice-verification.json").write_text(
        json.dumps(
            {
                "model": {"name": "m", "sha256": "injected"},
                "voices": {VOICE: {"passed": True}, CANDIDATE_VOICES[1]: {"passed": False}},
            }
        )
    )
    eng = engine(FakeVibeBackend(), allow_unverified_voices=False)
    assert eng.capabilities().voices == [VOICE]
    assert len(await collect(eng)) > 0


async def test_start_and_stop_are_idempotent():
    backend = FakeVibeBackend()
    eng = engine(backend)
    await eng.start()
    await eng.start()
    await eng.stop()
    await eng.stop()
    assert backend.closed == 1


async def test_queue_is_bounded():
    assert QUEUE_BLOCKS <= 16
    backend = FakeVibeBackend(ms_per_char=2000, block_ms=100)  # many blocks
    eng = engine(backend)
    cancel = CancelToken()
    gen = eng.synthesize("x" * 30, VOICE, cancel)
    await gen.__anext__()
    await asyncio.sleep(0.4)  # consumer idle: producer must block on the full queue
    assert backend.produced <= QUEUE_BLOCKS + 3
    cancel.cancel()
    await gen.aclose()


# -- error mapping ---------------------------------------------------------------------------


async def test_missing_model_dir_is_actionable(tmp_path):
    eng = VibeVoiceEngine(
        make_settings(
            engine="vibevoice",
            vibevoice_model_dir=str(tmp_path / "none"),
            allow_unverified_voices=True,
        )
    )
    with pytest.raises(EngineUnavailableError, match="download-models --engine vibevoice"):
        await eng.start()
    ok, reason, _ = eng.readiness()
    assert not ok and "download-models" in reason


async def test_memory_error_maps_to_out_of_memory():
    with pytest.raises(OutOfMemoryError):
        await collect(engine(FakeVibeBackend(fail_with=MemoryError())))


async def test_allocation_failure_maps_to_out_of_memory():
    with pytest.raises(OutOfMemoryError):
        await collect(engine(FakeVibeBackend(fail_with=RuntimeError("MPS backend out of memory"))))


async def test_other_failures_do_not_leak_text():
    with pytest.raises(EngineError) as ei:
        await collect(engine(FakeVibeBackend(fail_with=ValueError("secret user text"))))
    assert "secret" not in str(ei.value) and not isinstance(ei.value, OutOfMemoryError)


async def test_unverified_voice_is_refused():
    with pytest.raises(EngineError, match="not a verified Spanish voice"):
        await collect(engine(FakeVibeBackend()), voice="nope")


async def test_no_verified_voice_means_not_ready():
    eng = engine(FakeVibeBackend(), allow_unverified_voices=False)
    ok, reason, _ = eng.readiness()
    assert not ok and reason  # FR-007a: refuses instead of speaking unverified Spanish
    with pytest.raises(EngineError):
        await collect(eng)


# -- cancellation ----------------------------------------------------------------------------


async def test_cancel_stops_production_and_calls_stop_hook():
    backend = FakeVibeBackend(delay_s=0.02, ms_per_char=2000)
    eng = engine(backend)
    cancel = CancelToken()
    got = 0
    async for _ in eng.synthesize("x" * 40, VOICE, cancel):
        got += 1
        if got == 2:
            cancel.cancel()
    await asyncio.sleep(0.2)
    assert got <= 3
    assert backend.stop_seen
