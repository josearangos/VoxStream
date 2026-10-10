import asyncio
import uuid

from voxstream.config import Settings
from voxstream.core.session import Session
from voxstream.engines.mock import MockEngine
from voxstream.transports.websocket.framing import decode_frame


class Sink:
    """Collects what the session would write to the socket."""

    def __init__(self):
        self.frames: list[bytes] = []
        self.events: list[str] = []

    async def send_frame(self, data: bytes) -> None:
        self.frames.append(data)
        self.events.append("frame")


def make(engine=None, **kw):
    settings = Settings(_env_file=None, **kw)
    engine = engine or MockEngine()
    sink = Sink()
    s = Session(uuid.uuid4(), engine, "mock_es", settings, sink.send_frame)
    return s, sink, engine


async def test_segments_in_order_and_sequence_continuous():
    s, sink, engine = make()
    s.start()
    await s.feed("Primera frase. Segunda frase. ")
    await s.end()
    result = await s.wait()
    assert result.state == "COMPLETED"
    assert engine.synthesized == ["Primera frase.", "Segunda frase."]
    frames = [decode_frame(f) for f in sink.frames]
    assert [f.sequence for f in frames] == list(range(len(frames)))
    assert [f.last for f in frames[:-1]] == [False] * (len(frames) - 1)
    assert frames[-1].last


async def test_frames_sliced_to_frame_ms():
    s, sink, _ = make(frame_ms=100)
    s.start()
    await s.feed("Hola mundo.")
    await s.end()
    await s.wait()
    frames = [decode_frame(f) for f in sink.frames]
    full = 24000 * 100 // 1000 * 2
    # One segment: full frames, a short tail, then the empty frame carrying the last flag.
    assert all(len(f.payload) == full for f in frames[:-2])
    assert 0 < len(frames[-2].payload) <= full
    assert frames[-1].last and frames[-1].payload == b""


async def test_first_frame_before_end():
    s, sink, _ = make()
    s.start()
    await s.feed("Hola mundo. Y m")
    for _ in range(50):
        if sink.frames:
            break
        await asyncio.sleep(0.01)
    assert sink.frames, "audio must flow before end"
    await s.end()
    await s.wait()


async def test_single_piece_streams_by_segment():
    s, _, engine = make()
    s.start()
    await s.feed("Uno. Dos. Tres.")
    await s.end()
    await s.wait()
    assert len(engine.synthesized) == 3


async def test_streamed_equals_single_piece_text():
    text = "Hola, Sr. Pérez. Mide 3.5 metros. Adiós"
    s1, _, e1 = make()
    s1.start()
    await s1.feed(text)
    await s1.end()
    await s1.wait()
    s2, _, e2 = make()
    s2.start()
    for i in range(0, len(text), 5):
        await s2.feed(text[i : i + 5])
    await s2.end()
    await s2.wait()
    assert e1.synthesized == e2.synthesized


async def test_last_flag_only_on_final_frame_and_timing():
    s, sink, _ = make()
    s.start()
    await s.feed("Hola.")
    await s.end()
    result = await s.wait()
    frames = [decode_frame(f) for f in sink.frames]
    assert sum(f.last for f in frames) == 1
    assert result.audio_frames == len(frames)
    assert result.timing.rtf is not None
    assert result.chars == 5
