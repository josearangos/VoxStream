import re

import pytest

from voxstream.config import Settings
from voxstream.errors import CODE_CATEGORY, ErrorCode, VoxStreamError


def test_defaults():
    s = Settings(_env_file=None)
    assert s.host == "127.0.0.1" and s.port == 8765
    assert s.engine == "kokoro"
    assert s.max_text_chars == 2000
    assert s.request_timeout_s == 120 and s.idle_timeout_s == 15
    assert s.max_concurrent_requests == 1
    assert s.frame_ms == 100 and s.audio_queue_frames == 8 and s.max_pending_chars == 120
    assert s.execution_provider == "cpu"
    assert s.models_dir == "models"
    assert s.verification_file == "verification/voice-verification.json"
    assert s.default_voice is None


def test_env_override(monkeypatch):
    monkeypatch.setenv("VOXSTREAM_PORT", "9999")
    monkeypatch.setenv("VOXSTREAM_ENGINE", "mock")
    s = Settings(_env_file=None)
    assert s.port == 9999 and s.engine == "mock"


def test_every_code_has_category():
    assert set(CODE_CATEGORY) == set(ErrorCode)
    assert len(ErrorCode) == 15


@pytest.mark.parametrize("code", list(ErrorCode))
def test_error_message_has_no_path_or_traceback(code):
    err = VoxStreamError(code, "Something actionable happened.")
    assert err.category == CODE_CATEGORY[code]
    assert not re.search(r"(/Users/|/home/|Traceback|\.py\b)", err.message)
