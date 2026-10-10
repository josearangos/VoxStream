import pytest

from voxstream.config import Settings


def test_default_host_is_loopback():
    assert Settings(_env_file=None).host == "127.0.0.1"
    Settings(_env_file=None).validate_bind()


def test_non_local_bind_requires_explicit_setting():
    with pytest.raises(ValueError, match="ALLOW_NON_LOCAL_BIND"):
        Settings(_env_file=None, host="0.0.0.0").validate_bind()
    Settings(_env_file=None, host="0.0.0.0", allow_non_local_bind=True).validate_bind()


def test_grpc_default_binds_loopback_only():
    s = Settings(_env_file=None)
    assert s.enable_grpc and s.host == "127.0.0.1"
    s.validate_bind()  # one shared host for both transports
