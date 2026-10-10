"""Map protocol v1 error codes and local failures to plain-language messages."""

from __future__ import annotations

EMPTY_INPUT = "Enter some text first."
GENERIC = "The service reported an error ({code}). Try again."

_MESSAGES: dict[str, str] = {
    "MALFORMED_MESSAGE": "The demo sent a message the service did not understand. Try again.",
    "NO_ACTIVE_REQUEST": "The service has no active request. Try again.",
    "REQUEST_MISMATCH": "The service lost track of the request. Try again.",
    "BUSY": "The service is busy with another request. Try again in a moment.",
    "UNSUPPORTED_LANGUAGE": "The service only speaks Spanish.",
    "UNSUPPORTED_VOICE": "The selected voice is not available on the service.",
    "UNSUPPORTED_ENGINE": "The selected engine is not available on the service.",
    "TEXT_TOO_LONG": "Text is too long for the service. Shorten it and try again.",
    "EMPTY_REQUEST": "Enter some text first.",
    "IDLE_TIMEOUT": "The service timed out waiting for text. Try again.",
    "REQUEST_TIMEOUT": "The request took too long and was stopped. Try again.",
    "ENGINE_FAILURE": "The speech engine failed. Try again.",
    "ENGINE_UNAVAILABLE": "The speech engine is not ready yet. Try again in a moment.",
    "OUT_OF_MEMORY": "The service ran out of memory. Try shorter text.",
    "INTERNAL_ERROR": "The service hit an internal error. Try again.",
}


def too_long(limit: int) -> str:
    return f"Text is too long (max {limit} characters)."


def unreachable(url: str) -> str:
    return f"Can't reach the VoxStream service at {url}. Is it running?"


def message_for(code: str, *, limit: int | None = None) -> str:
    """Message for a service error code; unknown codes never echo server text."""
    if code == "TEXT_TOO_LONG" and limit is not None:
        return too_long(limit)
    known = _MESSAGES.get(code)
    if known is not None:
        return known
    return GENERIC.format(code="unknown")
