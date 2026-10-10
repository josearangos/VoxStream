import pytest
from demo.session import InvalidTransition, PlaybackSession, State


def test_happy_path() -> None:
    s = PlaybackSession()
    for st in (State.CONNECTING, State.PLAYING, State.FINISHED, State.READY):
        s.transition(st)
    assert s.state is State.READY and not s.active


def test_error_sets_message_and_clears() -> None:
    s = PlaybackSession()
    s.transition(State.CONNECTING)
    s.transition(State.ERROR, error="boom")
    assert s.error == "boom"
    s.transition(State.READY)
    assert s.error is None


@pytest.mark.parametrize("a,b", [(State.READY, State.PLAYING), (State.FINISHED, State.STOPPED)])
def test_invalid(a: State, b: State) -> None:
    with pytest.raises(InvalidTransition):
        PlaybackSession(state=a).transition(b)
