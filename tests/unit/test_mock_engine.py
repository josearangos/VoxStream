import pytest

from voxstream.engines.base import CancelToken, EngineError
from voxstream.engines.mock import MockEngine


async def collect(engine, text, cancel=None):
    return [b async for b in engine.synthesize(text, "mock_es", cancel or CancelToken())]


async def test_deterministic_and_length_function_of_text():
    e = MockEngine()
    a = await collect(e, "hola mundo")
    b = await collect(e, "hola mundo")
    assert sum(len(x.samples) for x in a) == sum(len(x.samples) for x in b)
    assert all((x.samples == y.samples).all() for x, y in zip(a, b, strict=True))
    short = sum(len(x.samples) for x in await collect(e, "hola"))
    long = sum(len(x.samples) for x in await collect(e, "hola hola hola"))
    assert long > short


async def test_cancel_stops_output():
    e = MockEngine()
    cancel = CancelToken()
    out = []
    async for blk in e.synthesize("x" * 200, "mock_es", cancel):
        out.append(blk)
        cancel.cancel()
    assert len(out) == 1


async def test_injected_failure():
    e = MockEngine(fail_at_segment=1)
    await collect(e, "uno")
    with pytest.raises(EngineError):
        await collect(e, "dos")


async def test_lifecycle_and_caps():
    e = MockEngine()
    await e.start()
    await e.stop()
    assert e.started and e.stopped
    caps = e.capabilities()
    assert caps.languages == ["es"] and caps.voices == ["mock_es"]
    assert caps.streaming_mode == "segmented"
