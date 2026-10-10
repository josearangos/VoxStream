import pytest

from helpers import make_settings
from voxstream.core.frames import AudioFrame
from voxstream.core.service import VoxStreamService
from voxstream.engines.base import EngineUnavailableError
from voxstream.engines.mock import MockEngine
from voxstream.errors import VoxStreamError


async def sink(_: AudioFrame) -> None:
    return None


def make(engine=None, **kw):
    return VoxStreamService(make_settings(**kw), engine or MockEngine())


async def open_(svc, **kw):
    args = {"engine": None, "voice": None, "language": None, **kw}
    return await svc.open_session(args["engine"], args["voice"], args["language"], sink)


async def code_of(svc, **kw):
    with pytest.raises(VoxStreamError) as exc:
        await open_(svc, **kw)
    return exc.value.code.value


async def test_error_codes():
    svc = make()
    assert await code_of(svc, engine="other") == "UNSUPPORTED_ENGINE"
    assert await code_of(svc, language="en") == "UNSUPPORTED_LANGUAGE"
    assert await code_of(svc, voice="nope") == "UNSUPPORTED_VOICE"
    assert svc.admission.active == 0
    assert await code_of(make(MockEngine(voices=[]))) == "ENGINE_UNAVAILABLE"


async def test_validation_order_engine_before_language_before_voice():
    svc = make()
    assert await code_of(svc, engine="x", language="en", voice="nope") == "UNSUPPORTED_ENGINE"
    assert await code_of(svc, language="en", voice="nope") == "UNSUPPORTED_LANGUAGE"


async def test_unsupported_voice_lists_available_voices():
    with pytest.raises(VoxStreamError) as exc:
        await open_(make(), voice="nope")
    assert "mock_es" in exc.value.message


async def test_default_voice_selection():
    opened = await open_(make())
    assert opened.info.voice == "mock_es" and opened.info.language == "es"
    opened.release()
    svc = make(MockEngine(voices=["a", "b"]), default_voice="b")
    assert (await open_(svc)).info.voice == "b"


async def test_second_open_at_limit_is_busy_and_release_is_idempotent():
    svc = make()
    first = await open_(svc)
    assert await code_of(svc) == "BUSY"
    first.release()
    first.release()
    assert svc.admission.active == 0
    (await open_(svc)).release()


async def test_slot_released_if_engine_start_fails():
    class Broken(MockEngine):
        async def start(self) -> None:
            raise EngineUnavailableError("/secret/model.onnx")

    svc = make(Broken())
    assert await code_of(svc) == "ENGINE_UNAVAILABLE"
    assert svc.admission.active == 0


async def test_engine_started_once():
    engine = MockEngine()
    svc = make(engine)
    for _ in range(2):
        (await open_(svc)).release()
    assert engine.started
