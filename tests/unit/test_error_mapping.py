from voxstream.core.session import map_exception
from voxstream.engines.base import EngineError, EngineUnavailableError, OutOfMemoryError
from voxstream.errors import ErrorCode, VoxStreamError


def test_mappings():
    assert map_exception(EngineError("x")).code == ErrorCode.ENGINE_FAILURE
    assert map_exception(OutOfMemoryError("x")).code == ErrorCode.OUT_OF_MEMORY
    assert map_exception(MemoryError()).code == ErrorCode.OUT_OF_MEMORY
    assert map_exception(EngineUnavailableError("x")).code == ErrorCode.ENGINE_UNAVAILABLE
    e = VoxStreamError(ErrorCode.BUSY, "b")
    assert map_exception(e) is e


def test_unexpected_is_generic_and_leak_free():
    err = map_exception(ValueError("/Users/me/secret.py line 3: hola"))
    assert err.code == ErrorCode.INTERNAL_ERROR
    assert "secret" not in err.message and "/Users" not in err.message
