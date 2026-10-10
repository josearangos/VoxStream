import pytest

from voxstream.core.admission import AdmissionController
from voxstream.errors import ErrorCode, VoxStreamError


def test_second_acquire_busy():
    a = AdmissionController(1)
    a.acquire()
    with pytest.raises(VoxStreamError) as ei:
        a.acquire()
    assert ei.value.code == ErrorCode.BUSY
    a.release()
    a.acquire()


def test_release_on_exception():
    a = AdmissionController(1)
    with pytest.raises(RuntimeError), a.slot():
        raise RuntimeError("boom")
    assert a.active == 0
    a.acquire()
