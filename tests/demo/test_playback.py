import asyncio
import io
import wave

from demo.playback import Runtime
from demo.session import State
from demo.settings import DemoSettings

TEXT = "Hola, ¿cómo estás hoy? Me alegra verte."


def settings(url: str, **kw: object) -> DemoSettings:
    return DemoSettings(service_url=url, **kw)  # type: ignore[arg-type]


async def test_full_playback_finishes(service_url: str) -> None:
    rt = Runtime(settings(service_url), TEXT)
    chunks = [c async for c in rt.run()]
    assert chunks and wave.open(io.BytesIO(chunks[0])).getframerate() == 24000
    assert rt.session.state is State.PLAYING and rt.session.total_audio_ms
    assert abs(rt.timeline.total_s - rt.session.total_audio_ms / 1000) < 1e-6
    await asyncio.sleep(rt.session.total_audio_ms / 1000 + 0.1)
    rt.tick()
    assert rt.status() == "Finished" and 'class="current"' not in rt.html()


async def test_position_never_ahead_of_received_audio(service_url: str) -> None:
    rt = Runtime(settings(service_url, playback_lead_ms=60_000), TEXT)
    async for _ in rt.run():
        break
    assert rt.position_s() <= rt.session.audio_ms_received / 1000


async def test_unreachable_sets_error() -> None:
    rt = Runtime(settings("ws://127.0.0.1:1/v1/stream"), TEXT)
    assert [c async for c in rt.run()] == []
    assert rt.session.state is State.ERROR and "Can't reach" in rt.status()
    assert not rt.active


async def test_service_error_message(short_limit_url: str) -> None:
    rt = Runtime(settings(short_limit_url, max_text_chars=10), TEXT)
    _ = [c async for c in rt.run()]
    assert rt.status() == "Error: Text is too long (max 10 characters)."


async def test_stop_keeps_spoken_words() -> None:
    rt = Runtime(settings("ws://x"), "uno dos")
    rt.session.transition(State.CONNECTING)
    rt.session.transition(State.PLAYING)
    rt.t0 = 0.0
    rt.stop()
    assert rt.status() == "Stopped" and not rt.active
