import uuid

from voxstream.core.frames import AudioFrame
from voxstream.core.metrics import RequestTiming, SegmentTiming
from voxstream.core.service import StreamInfo
from voxstream.core.session import SessionResult
from voxstream.engines.base import EngineCapabilities
from voxstream.errors import ErrorCode, VoxStreamError
from voxstream.transports.grpc import convert
from voxstream.transports.grpc.gen import voxstream_pb2 as pb


def test_audio_frame_round_trip_including_terminator_and_max_sequence():
    rid = uuid.uuid4()
    for frame in (
        AudioFrame(rid, 0, False, b"\x01\x02" * 100),
        AudioFrame(rid, 2**32 - 1, True, b""),
    ):
        chunk = pb.AudioChunk.FromString(convert.to_audio_chunk(frame).SerializeToString())
        assert (
            AudioFrame(uuid.UUID(chunk.request_id), chunk.sequence, chunk.last, chunk.pcm) == frame
        )


def _result(state="COMPLETED", timing=None, error=None):
    return SessionResult(state, 5, 480.04, 12, timing or RequestTiming(), error)


def test_completed_timing_map_is_all_doubles():
    t = RequestTiming()
    t.mark_first_text()
    t.mark_first_segment()
    t.mark_first_audio_sent()
    t.mark_end()
    t.segments.append(SegmentTiming(5, 10.0, 200.0))
    done = convert.to_completed("rid", _result(timing=t))
    assert done.request_id == "rid" and done.audio_frames == 5 and done.chars == 12
    assert done.audio_ms == 480.0
    assert "ttfa_from_first_segment_ms" in done.timing
    assert "segments" not in done.timing  # nested list is not a double
    assert all(isinstance(v, float) for v in done.timing.values())


def test_completed_drops_none_timing_values():
    done = convert.to_completed("rid", _result(timing=RequestTiming()))  # nothing marked
    assert "ttfa_from_first_segment_ms" not in done.timing
    assert "delivery_ms" not in done.timing


def test_cancelled():
    c = convert.to_cancelled("rid", _result("CANCELLED"))
    assert c.request_id == "rid" and c.audio_frames_sent == 5


def test_error_carries_all_fields_and_optional_request_id():
    err = VoxStreamError(ErrorCode.BUSY, "Try later.")
    rejected = convert.to_error(err)
    assert not rejected.HasField("request_id")
    assert (rejected.code, rejected.category, rejected.message, rejected.retryable) == (
        "BUSY",
        "capacity",
        "Try later.",
        True,
    )
    assert convert.to_error(err, "abc").request_id == "abc"


def test_start_unset_optionals_map_to_none():
    assert convert.from_start(pb.Start()) == (None, None, None)
    assert convert.from_start(pb.Start(voice="em_alex", language="es")) == (None, "em_alex", "es")
    assert convert.request_id_of(pb.Text(text="x")) is None
    assert convert.request_id_of(pb.End(request_id="r")) == "r"


def test_started_and_capabilities():
    info = StreamInfo(100, "v", "mock", "es", "segmented", "cpu")
    s = convert.to_started("rid", info)
    assert s.stream.sample_rate == 24000 and s.stream.encoding == "pcm_s16le"
    assert s.stream.channels == 1 and s.stream.voice == "v" and s.stream.frame_ms == 100
    caps = convert.capabilities_to_proto(EngineCapabilities("mock", "1", ["es"], ["v"]))
    assert list(caps.voices) == ["v"] and caps.sample_rate == 24000 and caps.supports_cancel
