import asyncio
import time

from helpers import SPANISH_PIECES, client_for, running_server
from voxstream.engines.mock import MockEngine


async def test_audio_arrives_before_last_piece_sent():
    engine = MockEngine(delay_s=0.01)
    async with running_server(engine) as server, client_for(server) as c:
        await c.start()
        first_audio: list[float] = []

        async def reader():
            frames = 0
            while True:
                m = await c.recv(10)
                if isinstance(m, bytes):
                    frames += 1
                    if not first_audio:
                        first_audio.append(time.monotonic())
                elif '"completed"' in m:
                    return frames

        task = asyncio.create_task(reader())
        pieces = [
            "Hola, ¿cómo estás hoy? ",
            "Me alegra verte. ",
            "Hoy hace un día muy ",
            "bonito. Y ",
            "mañana también.",
        ]
        for p in pieces:
            await c.text(p)
            await asyncio.sleep(0.15)
        last_sent = time.monotonic()
        await c.end()
        frames = await task
        assert frames > 0
        assert first_audio and first_audio[0] < last_sent  # SC-010


async def test_streamed_and_single_piece_speak_same_text():
    text = "".join(SPANISH_PIECES)
    spoken = []
    for pieces in ([text], SPANISH_PIECES):
        engine = MockEngine()
        async with running_server(engine) as server, client_for(server) as c:
            await c.start()
            for p in pieces:
                await c.text(p)
            await c.end()
            await c.collect()
        spoken.append(" ".join(engine.synthesized))
    assert spoken[0] == spoken[1] == " ".join(text.split())


# -- vibevoice over WebSocket with a stub backend (no model needed) ---------------------------


def _stub(name):
    from helpers import make_vibevoice_stub
    from voxstream.engines.mock import MockEngine

    return make_vibevoice_stub() if name == "vibevoice" else MockEngine(voices=["ef_dora"])


async def _run(name, **start):
    engine = _stub(name)
    async with running_server(engine, engine=name, enable_grpc=False) as server:
        async with client_for(server) as c:
            started = await c.start(**start)
            await c.text("Hola, ¿cómo estás? Hoy hace un día muy bonito.")
            await c.end()
            frames, controls = await c.collect()
        return started, frames, controls


async def test_vibevoice_flow_reports_engine_voice_and_completes():
    started, frames, controls = await _run("vibevoice")
    s = started["stream"]
    assert s["engine"] == "vibevoice" and s["encoding"] == "pcm_s16le"
    assert s["sample_rate"] == 24000 and s["channels"] == 1 and s["voice"]
    assert frames and [f.sequence for f in frames] == sorted(f.sequence for f in frames)
    assert frames[-1].last
    assert controls[-1]["type"] == "completed"


async def test_vibevoice_and_kokoro_style_engines_share_the_protocol_shape():
    shapes = {}
    for name in ("mock", "vibevoice"):
        started, frames, controls = await _run(name)
        shapes[name] = (
            sorted(started["stream"]),
            [c["type"] for c in controls],
            started["stream"]["encoding"],
            started["stream"]["sample_rate"],
            started["stream"]["frame_ms"],
            frames[-1].last,
        )
    assert shapes["mock"] == shapes["vibevoice"]  # SC-001: only engine and voice values differ


async def test_default_voice_is_first_verified_and_unknown_voice_is_rejected():
    from voxstream.engines.vibevoice.voices import CANDIDATE_VOICES

    started, _, _ = await _run("vibevoice")
    assert started["stream"]["voice"] == CANDIDATE_VOICES[0]
    engine = _stub("vibevoice")
    async with running_server(engine, engine="vibevoice", enable_grpc=False) as server:
        async with client_for(server) as c:
            reply = await c.start(voice="no-such-voice")
    assert reply["type"] == "error" and reply["code"] == "UNSUPPORTED_VOICE"
