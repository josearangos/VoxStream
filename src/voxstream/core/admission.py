"""Service-wide admission control with non-blocking acquire."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

from voxstream.errors import ErrorCode, VoxStreamError


class AdmissionController:
    def __init__(self, limit: int = 1) -> None:
        self.limit = limit
        self._active = 0

    @property
    def active(self) -> int:
        return self._active

    def acquire(self) -> None:
        if self._active >= self.limit:
            raise VoxStreamError(
                ErrorCode.BUSY,
                "The service is at its concurrent request limit; retry when the active "
                "request has finished.",
            )
        self._active += 1

    def release(self) -> None:
        if self._active > 0:
            self._active -= 1

    @contextmanager
    def slot(self) -> Iterator[None]:
        self.acquire()
        try:
            yield
        finally:
            self.release()
