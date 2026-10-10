"""JSON control messages (see contracts/websocket-protocol.md)."""

from __future__ import annotations

import json
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter, ValidationError

from voxstream.errors import ErrorCode, VoxStreamError


class _Msg(BaseModel):
    model_config = ConfigDict(extra="ignore")


class StartMsg(_Msg):
    type: Literal["start"]
    engine: str | None = None
    voice: str | None = None
    language: str | None = None


class TextMsg(_Msg):
    type: Literal["text"]
    request_id: str
    text: str


class EndMsg(_Msg):
    type: Literal["end"]
    request_id: str


class CancelMsg(_Msg):
    type: Literal["cancel"]
    request_id: str


class CapabilitiesMsg(_Msg):
    type: Literal["capabilities"]


ClientMessage = Annotated[
    StartMsg | TextMsg | EndMsg | CancelMsg | CapabilitiesMsg, Field(discriminator="type")
]
_client_adapter: TypeAdapter[ClientMessage] = TypeAdapter(ClientMessage)


AnyClientMessage = StartMsg | TextMsg | EndMsg | CancelMsg | CapabilitiesMsg


def parse_client_message(raw: str | bytes) -> AnyClientMessage:
    try:
        data = json.loads(raw)
        return _client_adapter.validate_python(data)
    except (ValueError, ValidationError):
        raise VoxStreamError(
            ErrorCode.MALFORMED_MESSAGE,
            "Message is not valid JSON, has an unknown 'type', or is missing a required field.",
        ) from None


class StreamDescriptor(BaseModel):
    encoding: str = "pcm_s16le"
    sample_rate: int = 24000
    channels: int = 1
    frame_ms: int
    voice: str
    engine: str
    language: str
    streaming_mode: str
    execution_provider: str


def started(request_id: str, stream: StreamDescriptor) -> dict[str, Any]:
    return {"type": "started", "request_id": request_id, "stream": stream.model_dump()}


def completed(
    request_id: str, audio_frames: int, audio_ms: float, chars: int, timing: dict[str, Any]
) -> dict[str, Any]:
    return {
        "type": "completed",
        "request_id": request_id,
        "audio_frames": audio_frames,
        "audio_ms": round(audio_ms, 1),
        "chars": chars,
        "timing": timing,
    }


def cancelled(request_id: str, audio_frames_sent: int) -> dict[str, Any]:
    return {"type": "cancelled", "request_id": request_id, "audio_frames_sent": audio_frames_sent}


def error(err: VoxStreamError, request_id: str | None = None) -> dict[str, Any]:
    return {
        "type": "error",
        "request_id": request_id if request_id is not None else err.request_id,
        "code": err.code.value,
        "category": err.category.value,
        "message": err.message,
        "retryable": err.retryable,
    }
