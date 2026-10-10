import pytest

from voxstream.config import Settings
from voxstream.engines.mock import MockEngine
from voxstream.engines.registry import create_engine
from voxstream.errors import ErrorCode, VoxStreamError


def test_mock_selected():
    assert isinstance(create_engine("mock", Settings(_env_file=None)), MockEngine)


def test_unknown_engine():
    with pytest.raises(VoxStreamError) as ei:
        create_engine("nope", Settings(_env_file=None))
    assert ei.value.code == ErrorCode.UNSUPPORTED_ENGINE
    assert "kokoro" in ei.value.message
