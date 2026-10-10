"""Pure conversions between ``core`` types and the generated protobuf messages."""

from __future__ import annotations

from voxstream.core.frames import AudioFrame
from voxstream.core.service import StreamInfo
from voxstream.core.session import SessionResult
from voxstream.engines.base import EngineCapabilities
from voxstream.errors import VoxStreamError
from voxstream.transports.grpc.gen import voxstream_pb2 as pb


def to_audio_chunk(frame: AudioFrame) -> pb.AudioChunk:
    return pb.AudioChunk(
        request_id=str(frame.request_id), sequence=frame.sequence, last=frame.last, pcm=frame.pcm
    )


def to_started(request_id: str, info: StreamInfo) -> pb.Started:
    return pb.Started(
        request_id=request_id,
        stream=pb.StreamDescriptor(
            encoding=info.encoding,
            sample_rate=info.sample_rate,
            channels=info.channels,
            frame_ms=info.frame_ms,
            voice=info.voice,
            engine=info.engine,
            language=info.language,
            streaming_mode=info.streaming_mode,
            execution_provider=info.execution_provider,
        ),
    )


def to_completed(request_id: str, result: SessionResult) -> pb.Completed:
    # The map carries doubles only: drop None values and the nested per-segment list.
    timing = {
        k: float(v)
        for k, v in result.timing.to_dict().items()
        if isinstance(v, int | float) and not isinstance(v, bool)
    }
    return pb.Completed(
        request_id=request_id,
        audio_frames=result.audio_frames,
        audio_ms=round(result.audio_ms, 1),
        chars=result.chars,
        timing=timing,
    )


def to_cancelled(request_id: str, result: SessionResult) -> pb.Cancelled:
    return pb.Cancelled(request_id=request_id, audio_frames_sent=result.audio_frames)


def to_error(err: VoxStreamError, request_id: str | None = None) -> pb.Error:
    rid = request_id if request_id is not None else err.request_id
    return pb.Error(
        request_id=rid,
        code=err.code.value,
        category=err.category.value,
        message=err.message,
        retryable=err.retryable,
    )


def capabilities_to_proto(caps: EngineCapabilities) -> pb.Capabilities:
    return pb.Capabilities(
        engine=caps.name,
        version=caps.version,
        languages=caps.languages,
        voices=caps.voices,
        encoding=caps.audio_format.encoding,
        sample_rate=caps.audio_format.sample_rate,
        channels=caps.audio_format.channels,
        streaming_mode=caps.streaming_mode,
        supports_cancel=bool(caps.supports_cancel),
        execution_provider=caps.execution_provider,
        memory_notes=caps.memory_notes,
    )


def from_start(m: pb.Start) -> tuple[str | None, str | None, str | None]:
    """Return (engine, voice, language); unset optional fields are ``None``."""
    return (
        m.engine if m.HasField("engine") else None,
        m.voice if m.HasField("voice") else None,
        m.language if m.HasField("language") else None,
    )


def request_id_of(m: pb.Text | pb.End | pb.Cancel) -> str | None:
    return m.request_id if m.HasField("request_id") else None
