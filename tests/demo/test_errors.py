import pytest

from demo import errors

CODES = [
    "MALFORMED_MESSAGE", "NO_ACTIVE_REQUEST", "REQUEST_MISMATCH", "BUSY", "UNSUPPORTED_LANGUAGE",
    "UNSUPPORTED_VOICE", "UNSUPPORTED_ENGINE", "TEXT_TOO_LONG", "EMPTY_REQUEST", "IDLE_TIMEOUT",
    "REQUEST_TIMEOUT", "ENGINE_FAILURE", "ENGINE_UNAVAILABLE", "OUT_OF_MEMORY", "INTERNAL_ERROR",
]  # fmt: skip


@pytest.mark.parametrize("code", CODES)
def test_every_code_has_message(code: str) -> None:
    assert errors.message_for(code)


def test_unknown_code_is_generic_and_does_not_echo() -> None:
    msg = errors.message_for("<script>evil</script>")
    assert "evil" not in msg and msg == errors.GENERIC.format(code="unknown")


def test_too_long_shows_limit() -> None:
    assert "2000" in errors.message_for("TEXT_TOO_LONG", limit=2000)
    assert "2000" in errors.too_long(2000)


def test_unreachable_has_url() -> None:
    assert "ws://x" in errors.unreachable("ws://x")
