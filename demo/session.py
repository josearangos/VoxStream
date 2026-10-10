"""Playback session state and transitions (data-model.md)."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class State(StrEnum):
    READY = "ready"
    CONNECTING = "connecting"
    PLAYING = "playing"
    FINISHED = "finished"
    STOPPED = "stopped"
    ERROR = "error"


_ALLOWED: dict[State, frozenset[State]] = {
    State.READY: frozenset({State.CONNECTING}),
    State.CONNECTING: frozenset({State.PLAYING, State.STOPPED, State.ERROR}),
    State.PLAYING: frozenset({State.FINISHED, State.STOPPED, State.ERROR}),
    State.FINISHED: frozenset({State.READY}),
    State.STOPPED: frozenset({State.READY}),
    State.ERROR: frozenset({State.READY}),
}


class InvalidTransition(Exception):
    pass


@dataclass
class PlaybackSession:
    text: str = ""
    state: State = State.READY
    request_id: str | None = None
    audio_ms_received: float = 0.0
    total_audio_ms: float | None = None
    error: str | None = None

    @property
    def active(self) -> bool:
        return self.state in (State.CONNECTING, State.PLAYING)

    def transition(self, new: State, *, error: str | None = None) -> None:
        if new not in _ALLOWED[self.state]:
            raise InvalidTransition(f"{self.state} -> {new}")
        self.state = new
        self.error = error if new is State.ERROR else None
