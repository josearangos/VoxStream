import asyncio

import pytest
from grpc import aio

from helpers import running_server
from voxstream.engines.mock import MockEngine
from voxstream.transports.grpc import server as grpc_server
from voxstream.transports.grpc.gen import voxstream_pb2 as pb
from voxstream.transports.grpc.gen import voxstream_pb2_grpc as pb_grpc

SENTENCE = "Esta es una oración de prueba bastante larga para generar audio. "


@pytest.fixture
def calls(monkeypatch):
    seen: list[grpc_server._Call] = []

    class Recording(grpc_server._Call):
        def __init__(self, *a, **kw):
            super().__init__(*a, **kw)
            seen.append(self)

    monkeypatch.setattr(grpc_server, "_Call", Recording)
    return seen


async def test_stalled_client_keeps_buffers_bounded_and_synthesis_pauses(calls):
    engine = MockEngine()
    async with running_server(engine, audio_queue_frames=8, max_pending_chars=120) as server:
        # No BDP probing so the HTTP/2 window stays small and the stall is deterministic.
        options = [("grpc.http2.bdp_probe", 0), ("grpc.initial_reconnect_backoff_ms", 100)]
        async with aio.insecure_channel(f"127.0.0.1:{server.grpc_port}", options=options) as ch:
            stub = pb_grpc.SynthesizerStub(ch)
            outbound: asyncio.Queue[pb.ClientEvent | None] = asyncio.Queue()

            async def requests():
                while (ev := await outbound.get()) is not None:
                    yield ev

            call = stub.Stream(requests())
            outbound.put_nowait(pb.ClientEvent(start=pb.Start()))
            first = await call.read()
            assert first.WhichOneof("event") == "started"
            text = SENTENCE * 28  # < 2000 chars, ~70 s of mock audio (several MB)
            for i in range(0, len(text), 400):
                outbound.put_nowait(pb.ClientEvent(text=pb.Text(text=text[i : i + 400])))
            audio = await call.read()
            assert audio.WhichOneof("event") == "audio"
            (c,) = calls
            assert c.session is not None
            max_out = max_audio = max_seg = 0
            for _ in range(40):  # the client now stalls
                await asyncio.sleep(0.05)
                max_out = max(max_out, c.outbox.qsize())
                max_audio = max(max_audio, c.session.audio_queue.qsize())
                max_seg = max(max_seg, c.session.segment_queue.qsize())
                assert c.inbox.qsize() <= grpc_server.INBOX_SIZE
            assert max_out <= grpc_server.OUTBOX_SIZE
            assert max_audio <= 8 and max_seg <= 4
            synthesized = engine.calls
            await asyncio.sleep(0.5)
            assert engine.calls == synthesized, "synthesis must pause while the client stalls"
            assert engine.calls < 28, "the whole text must not be synthesized into memory"
            outbound.put_nowait(pb.ClientEvent(cancel=pb.Cancel()))
            outbound.put_nowait(None)
            while await call.read() is not aio.EOF:
                pass
        assert server.admission.active == 0
