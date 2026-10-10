import uuid

from helpers import SPANISH_PIECES, client_for


async def test_full_stream_flow(serve):
    async with serve() as server, client_for(server) as c:
        started = await c.start()
        assert started["type"] == "started"
        uuid.UUID(started["request_id"])
        s = started["stream"]
        assert s["encoding"] == "pcm_s16le" and s["sample_rate"] == 24000 and s["channels"] == 1
        assert s["language"] == "es" and s["frame_ms"] == 100
        assert s["streaming_mode"] in ("incremental", "segmented", "complete_then_chunked")
        assert s["voice"] and s["engine"] and s["execution_provider"]

        for piece in SPANISH_PIECES:
            await c.text(piece)
        await c.end()
        frames, controls = await c.collect(timeout=120)

        assert [f.sequence for f in frames] == list(range(len(frames)))
        assert all(str(f.request_id) == c.request_id for f in frames)
        assert frames[-1].last and not any(f.last for f in frames[:-1])
        terminals = [m for m in controls if m["type"] in ("completed", "cancelled", "error")]
        assert len(terminals) == 1 and terminals[0]["type"] == "completed"
        done = terminals[0]
        assert done["audio_frames"] == len(frames)
        assert done["chars"] == sum(len(p) for p in SPANISH_PIECES)
        # decodable from the descriptor alone: whole 16-bit samples at 24 kHz
        assert all(len(f.payload) % 2 == 0 for f in frames)
        assert done["timing"]["ttfa_from_first_segment_ms"] is not None


async def test_default_voice_reported_when_omitted(serve):
    async with serve() as server, client_for(server) as c:
        started = await c.start()
        caps_voices = None
        await c.cancel()
        await c.collect()
        await c.send(type="capabilities")
        caps = await c.recv_json()
        caps_voices = caps["voices"]
        assert started["stream"]["voice"] in caps_voices


async def test_connection_reusable_after_completion(serve):
    async with serve() as server, client_for(server) as c:
        for _ in range(2):
            assert (await c.start())["type"] == "started"
            await c.text("Hola mundo.")
            await c.end()
            _, controls = await c.collect(timeout=120)
            assert controls[-1]["type"] == "completed"
