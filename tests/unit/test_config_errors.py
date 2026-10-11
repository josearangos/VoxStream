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


def test_transport_defaults():
    s = Settings(_env_file=None)
    assert s.enable_websocket is True and s.enable_grpc is True
    assert s.grpc_port == 50051
    s.validate_transports()


def test_both_transports_disabled_is_an_actionable_error():
    s = Settings(_env_file=None, enable_websocket=False, enable_grpc=False)
    with pytest.raises(ValueError, match="At least one of the two transports") as exc:
        s.validate_transports()
    assert "VOXSTREAM_ENABLE_WEBSOCKET" in str(exc.value)
    assert "VOXSTREAM_ENABLE_GRPC" in str(exc.value)


def test_transport_env_override(monkeypatch):
    monkeypatch.setenv("VOXSTREAM_ENABLE_GRPC", "false")
    monkeypatch.setenv("VOXSTREAM_GRPC_PORT", "6000")
    s = Settings(_env_file=None)
    assert s.enable_grpc is False and s.grpc_port == 6000


def test_grpc_port_must_differ_from_port_unless_ephemeral():
    with pytest.raises(ValueError, match="VOXSTREAM_GRPC_PORT"):
        Settings(_env_file=None, port=9000, grpc_port=9000).validate_transports()
    Settings(_env_file=None, port=0, grpc_port=0).validate_transports()


def test_vibevoice_with_grpc_enabled_is_refused():
    s = Settings(_env_file=None, engine="vibevoice", enable_grpc=True)
    with pytest.raises(ValueError) as exc:
        s.validate_transports()
    assert str(exc.value) == (
        "engine 'vibevoice' is not supported on the gRPC transport; "
        "set VOXSTREAM_ENABLE_GRPC=false."
    )


def test_vibevoice_with_grpc_disabled_passes():
    Settings(_env_file=None, engine="vibevoice", enable_grpc=False).validate_transports()


def test_vibevoice_defaults_and_verification_path():
    s = Settings(_env_file=None, engine="vibevoice")
    assert s.vibevoice_model_dir == "models/vibevoice" and s.vibevoice_device == "cpu"
    assert s.engine_verification_file == "verification/vibevoice-verification.json"
    assert Settings(_env_file=None).engine_verification_file == s.verification_file
