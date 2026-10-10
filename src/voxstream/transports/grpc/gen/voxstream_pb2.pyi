from google.protobuf.internal import containers as _containers
from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from collections.abc import Iterable as _Iterable, Mapping as _Mapping
from typing import ClassVar as _ClassVar, Optional as _Optional, Union as _Union

DESCRIPTOR: _descriptor.FileDescriptor

class ClientEvent(_message.Message):
    __slots__ = ("start", "text", "end", "cancel")
    START_FIELD_NUMBER: _ClassVar[int]
    TEXT_FIELD_NUMBER: _ClassVar[int]
    END_FIELD_NUMBER: _ClassVar[int]
    CANCEL_FIELD_NUMBER: _ClassVar[int]
    start: Start
    text: Text
    end: End
    cancel: Cancel
    def __init__(self, start: _Optional[_Union[Start, _Mapping]] = ..., text: _Optional[_Union[Text, _Mapping]] = ..., end: _Optional[_Union[End, _Mapping]] = ..., cancel: _Optional[_Union[Cancel, _Mapping]] = ...) -> None: ...

class Start(_message.Message):
    __slots__ = ("engine", "voice", "language")
    ENGINE_FIELD_NUMBER: _ClassVar[int]
    VOICE_FIELD_NUMBER: _ClassVar[int]
    LANGUAGE_FIELD_NUMBER: _ClassVar[int]
    engine: str
    voice: str
    language: str
    def __init__(self, engine: _Optional[str] = ..., voice: _Optional[str] = ..., language: _Optional[str] = ...) -> None: ...

class Text(_message.Message):
    __slots__ = ("text", "request_id")
    TEXT_FIELD_NUMBER: _ClassVar[int]
    REQUEST_ID_FIELD_NUMBER: _ClassVar[int]
    text: str
    request_id: str
    def __init__(self, text: _Optional[str] = ..., request_id: _Optional[str] = ...) -> None: ...

class End(_message.Message):
    __slots__ = ("request_id",)
    REQUEST_ID_FIELD_NUMBER: _ClassVar[int]
    request_id: str
    def __init__(self, request_id: _Optional[str] = ...) -> None: ...

class Cancel(_message.Message):
    __slots__ = ("request_id",)
    REQUEST_ID_FIELD_NUMBER: _ClassVar[int]
    request_id: str
    def __init__(self, request_id: _Optional[str] = ...) -> None: ...

class ServerEvent(_message.Message):
    __slots__ = ("started", "audio", "completed", "cancelled", "error")
    STARTED_FIELD_NUMBER: _ClassVar[int]
    AUDIO_FIELD_NUMBER: _ClassVar[int]
    COMPLETED_FIELD_NUMBER: _ClassVar[int]
    CANCELLED_FIELD_NUMBER: _ClassVar[int]
    ERROR_FIELD_NUMBER: _ClassVar[int]
    started: Started
    audio: AudioChunk
    completed: Completed
    cancelled: Cancelled
    error: Error
    def __init__(self, started: _Optional[_Union[Started, _Mapping]] = ..., audio: _Optional[_Union[AudioChunk, _Mapping]] = ..., completed: _Optional[_Union[Completed, _Mapping]] = ..., cancelled: _Optional[_Union[Cancelled, _Mapping]] = ..., error: _Optional[_Union[Error, _Mapping]] = ...) -> None: ...

class StreamDescriptor(_message.Message):
    __slots__ = ("encoding", "sample_rate", "channels", "frame_ms", "voice", "engine", "language", "streaming_mode", "execution_provider")
    ENCODING_FIELD_NUMBER: _ClassVar[int]
    SAMPLE_RATE_FIELD_NUMBER: _ClassVar[int]
    CHANNELS_FIELD_NUMBER: _ClassVar[int]
    FRAME_MS_FIELD_NUMBER: _ClassVar[int]
    VOICE_FIELD_NUMBER: _ClassVar[int]
    ENGINE_FIELD_NUMBER: _ClassVar[int]
    LANGUAGE_FIELD_NUMBER: _ClassVar[int]
    STREAMING_MODE_FIELD_NUMBER: _ClassVar[int]
    EXECUTION_PROVIDER_FIELD_NUMBER: _ClassVar[int]
    encoding: str
    sample_rate: int
    channels: int
    frame_ms: int
    voice: str
    engine: str
    language: str
    streaming_mode: str
    execution_provider: str
    def __init__(self, encoding: _Optional[str] = ..., sample_rate: _Optional[int] = ..., channels: _Optional[int] = ..., frame_ms: _Optional[int] = ..., voice: _Optional[str] = ..., engine: _Optional[str] = ..., language: _Optional[str] = ..., streaming_mode: _Optional[str] = ..., execution_provider: _Optional[str] = ...) -> None: ...

class Started(_message.Message):
    __slots__ = ("request_id", "stream")
    REQUEST_ID_FIELD_NUMBER: _ClassVar[int]
    STREAM_FIELD_NUMBER: _ClassVar[int]
    request_id: str
    stream: StreamDescriptor
    def __init__(self, request_id: _Optional[str] = ..., stream: _Optional[_Union[StreamDescriptor, _Mapping]] = ...) -> None: ...

class AudioChunk(_message.Message):
    __slots__ = ("request_id", "sequence", "last", "pcm")
    REQUEST_ID_FIELD_NUMBER: _ClassVar[int]
    SEQUENCE_FIELD_NUMBER: _ClassVar[int]
    LAST_FIELD_NUMBER: _ClassVar[int]
    PCM_FIELD_NUMBER: _ClassVar[int]
    request_id: str
    sequence: int
    last: bool
    pcm: bytes
    def __init__(self, request_id: _Optional[str] = ..., sequence: _Optional[int] = ..., last: _Optional[bool] = ..., pcm: _Optional[bytes] = ...) -> None: ...

class Completed(_message.Message):
    __slots__ = ("request_id", "audio_frames", "audio_ms", "chars", "timing")
    class TimingEntry(_message.Message):
        __slots__ = ("key", "value")
        KEY_FIELD_NUMBER: _ClassVar[int]
        VALUE_FIELD_NUMBER: _ClassVar[int]
        key: str
        value: float
        def __init__(self, key: _Optional[str] = ..., value: _Optional[float] = ...) -> None: ...
    REQUEST_ID_FIELD_NUMBER: _ClassVar[int]
    AUDIO_FRAMES_FIELD_NUMBER: _ClassVar[int]
    AUDIO_MS_FIELD_NUMBER: _ClassVar[int]
    CHARS_FIELD_NUMBER: _ClassVar[int]
    TIMING_FIELD_NUMBER: _ClassVar[int]
    request_id: str
    audio_frames: int
    audio_ms: float
    chars: int
    timing: _containers.ScalarMap[str, float]
    def __init__(self, request_id: _Optional[str] = ..., audio_frames: _Optional[int] = ..., audio_ms: _Optional[float] = ..., chars: _Optional[int] = ..., timing: _Optional[_Mapping[str, float]] = ...) -> None: ...

class Cancelled(_message.Message):
    __slots__ = ("request_id", "audio_frames_sent")
    REQUEST_ID_FIELD_NUMBER: _ClassVar[int]
    AUDIO_FRAMES_SENT_FIELD_NUMBER: _ClassVar[int]
    request_id: str
    audio_frames_sent: int
    def __init__(self, request_id: _Optional[str] = ..., audio_frames_sent: _Optional[int] = ...) -> None: ...

class Error(_message.Message):
    __slots__ = ("request_id", "code", "category", "message", "retryable")
    REQUEST_ID_FIELD_NUMBER: _ClassVar[int]
    CODE_FIELD_NUMBER: _ClassVar[int]
    CATEGORY_FIELD_NUMBER: _ClassVar[int]
    MESSAGE_FIELD_NUMBER: _ClassVar[int]
    RETRYABLE_FIELD_NUMBER: _ClassVar[int]
    request_id: str
    code: str
    category: str
    message: str
    retryable: bool
    def __init__(self, request_id: _Optional[str] = ..., code: _Optional[str] = ..., category: _Optional[str] = ..., message: _Optional[str] = ..., retryable: _Optional[bool] = ...) -> None: ...

class CapabilitiesRequest(_message.Message):
    __slots__ = ()
    def __init__(self) -> None: ...

class Capabilities(_message.Message):
    __slots__ = ("engine", "version", "languages", "voices", "encoding", "sample_rate", "channels", "streaming_mode", "supports_cancel", "execution_provider", "memory_notes")
    ENGINE_FIELD_NUMBER: _ClassVar[int]
    VERSION_FIELD_NUMBER: _ClassVar[int]
    LANGUAGES_FIELD_NUMBER: _ClassVar[int]
    VOICES_FIELD_NUMBER: _ClassVar[int]
    ENCODING_FIELD_NUMBER: _ClassVar[int]
    SAMPLE_RATE_FIELD_NUMBER: _ClassVar[int]
    CHANNELS_FIELD_NUMBER: _ClassVar[int]
    STREAMING_MODE_FIELD_NUMBER: _ClassVar[int]
    SUPPORTS_CANCEL_FIELD_NUMBER: _ClassVar[int]
    EXECUTION_PROVIDER_FIELD_NUMBER: _ClassVar[int]
    MEMORY_NOTES_FIELD_NUMBER: _ClassVar[int]
    engine: str
    version: str
    languages: _containers.RepeatedScalarFieldContainer[str]
    voices: _containers.RepeatedScalarFieldContainer[str]
    encoding: str
    sample_rate: int
    channels: int
    streaming_mode: str
    supports_cancel: bool
    execution_provider: str
    memory_notes: str
    def __init__(self, engine: _Optional[str] = ..., version: _Optional[str] = ..., languages: _Optional[_Iterable[str]] = ..., voices: _Optional[_Iterable[str]] = ..., encoding: _Optional[str] = ..., sample_rate: _Optional[int] = ..., channels: _Optional[int] = ..., streaming_mode: _Optional[str] = ..., supports_cancel: _Optional[bool] = ..., execution_provider: _Optional[str] = ..., memory_notes: _Optional[str] = ...) -> None: ...
