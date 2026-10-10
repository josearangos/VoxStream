"""Stable error codes and the structured service error."""

from __future__ import annotations

from enum import StrEnum


class ErrorCategory(StrEnum):
    VALIDATION = "validation"
    CAPACITY = "capacity"
    ENGINE = "engine"
    TIMEOUT = "timeout"
    PROTOCOL = "protocol"
    INTERNAL = "internal"


class ErrorCode(StrEnum):
    MALFORMED_MESSAGE = "MALFORMED_MESSAGE"
    NO_ACTIVE_REQUEST = "NO_ACTIVE_REQUEST"
    REQUEST_MISMATCH = "REQUEST_MISMATCH"
    BUSY = "BUSY"
    UNSUPPORTED_LANGUAGE = "UNSUPPORTED_LANGUAGE"
    UNSUPPORTED_VOICE = "UNSUPPORTED_VOICE"
    UNSUPPORTED_ENGINE = "UNSUPPORTED_ENGINE"
    TEXT_TOO_LONG = "TEXT_TOO_LONG"
    EMPTY_REQUEST = "EMPTY_REQUEST"
    IDLE_TIMEOUT = "IDLE_TIMEOUT"
    REQUEST_TIMEOUT = "REQUEST_TIMEOUT"
    ENGINE_FAILURE = "ENGINE_FAILURE"
    ENGINE_UNAVAILABLE = "ENGINE_UNAVAILABLE"
    OUT_OF_MEMORY = "OUT_OF_MEMORY"
    INTERNAL_ERROR = "INTERNAL_ERROR"


_C = ErrorCategory

CODE_CATEGORY: dict[ErrorCode, ErrorCategory] = {
    ErrorCode.MALFORMED_MESSAGE: _C.PROTOCOL,
    ErrorCode.NO_ACTIVE_REQUEST: _C.PROTOCOL,
    ErrorCode.REQUEST_MISMATCH: _C.PROTOCOL,
    ErrorCode.BUSY: _C.CAPACITY,
    ErrorCode.UNSUPPORTED_LANGUAGE: _C.VALIDATION,
    ErrorCode.UNSUPPORTED_VOICE: _C.VALIDATION,
    ErrorCode.UNSUPPORTED_ENGINE: _C.VALIDATION,
    ErrorCode.TEXT_TOO_LONG: _C.VALIDATION,
    ErrorCode.EMPTY_REQUEST: _C.VALIDATION,
    ErrorCode.IDLE_TIMEOUT: _C.TIMEOUT,
    ErrorCode.REQUEST_TIMEOUT: _C.TIMEOUT,
    ErrorCode.ENGINE_FAILURE: _C.ENGINE,
    ErrorCode.ENGINE_UNAVAILABLE: _C.ENGINE,
    ErrorCode.OUT_OF_MEMORY: _C.ENGINE,
    ErrorCode.INTERNAL_ERROR: _C.INTERNAL,
}

RETRYABLE: frozenset[ErrorCode] = frozenset(
    {ErrorCode.BUSY, ErrorCode.IDLE_TIMEOUT, ErrorCode.REQUEST_TIMEOUT}
)


class VoxStreamError(Exception):
    """An error that maps directly to a protocol ``error`` message.

    The message must be actionable and must not contain stack traces, file paths or input text.
    """

    def __init__(
        self,
        code: ErrorCode,
        message: str,
        *,
        retryable: bool | None = None,
        request_id: str | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.category = CODE_CATEGORY[code]
        self.message = message
        self.retryable = code in RETRYABLE if retryable is None else retryable
        self.request_id = request_id
