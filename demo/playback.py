"""Playback runtime: ties the stream client, session state and teleprompter timeline together."""

from __future__ import annotations

import logging
import time
from collections.abc import AsyncIterator
from dataclasses import dataclass, field

from demo import errors, teleprompter
from demo.audio import pcm_to_wav_chunk
from demo.session import PlaybackSession, State
from demo.settings import DemoSettings
from demo.stream_client import (
    AudioChunk,
    Completed,
    ServiceError,
    ServiceUnreachable,
    Started,
    UnsupportedStream,
    stream_speech,
)
from demo.timeline import Timeline, build_timeline

log = logging.getLogger("demo")

STATUS_TEXT = {
    State.READY: "Ready",
    State.CONNECTING: "Connecting…",
    State.PLAYING: "Playing",
    State.FINISHED: "Finished",
    State.STOPPED: "Stopped",
}
PREPARING_TEXT = "Preparing speech…"


@dataclass
class Runtime:
    """One playback. Position is estimated from wall-clock time since the first audio chunk,
    never ahead of the audio received so far (research R2 fallback, see T018 notes)."""

    settings: DemoSettings
    text: str
    session: PlaybackSession = field(default_factory=PlaybackSession)
    timeline: Timeline = field(init=False)
    t0: float | None = None
    frozen_index: int | None = None
    sample_rate: int = 24000
    channels: int = 1
    voice: str | None = None
    engine: str | None = None
    error_code: str | None = None

    def __post_init__(self) -> None:
        s = self.settings
        self.session.text = self.text
        self.timeline = build_timeline(
            self.text,
            s.speech_rate_chars_per_s,
            pause_comma=s.pause_weight_comma,
            pause_sentence=s.pause_weight_sentence,
            pause_linebreak=s.pause_weight_linebreak,
        )

    def _go(self, state: State, *, error: str | None = None) -> None:
        if self.session.state is state:
            return
        self.session.transition(state, error=error)
        log.info("request=%s state=%s", self.session.request_id, state.value)

    def position_s(self) -> float:
        if self.t0 is None:
            return 0.0
        elapsed = time.monotonic() - self.t0 + self.settings.playback_lead_ms / 1000
        return min(elapsed, self.session.audio_ms_received / 1000)

    def current_index(self) -> int:
        if self.frozen_index is not None:
            return self.frozen_index
        if self.t0 is None:
            return -1
        return self.timeline.word_at(self.position_s())

    def tick(self) -> None:
        """Advance Playing -> Finished once the audio has played out."""
        s = self.session
        if s.state is State.PLAYING and s.total_audio_ms is not None:
            if self.position_s() >= s.total_audio_ms / 1000:
                self._go(State.FINISHED)

    def stop(self) -> None:
        if self.session.active:
            self.frozen_index = self.current_index()
            self._go(State.STOPPED)

    def fail(self, message: str) -> None:
        if self.session.active:
            self.frozen_index = self.current_index()
            self._go(State.ERROR, error=message)

    @property
    def active(self) -> bool:
        return self.session.active

    def status(self) -> str:
        if self.session.state is State.ERROR:
            return f"Error: {self.session.error}"
        if self.session.state is State.PLAYING and self.t0 is None:
            return PREPARING_TEXT
        return STATUS_TEXT[self.session.state]

    def html(self) -> str:
        finished = self.session.state is State.FINISHED
        return teleprompter.render(self.text, self.timeline.words, self.current_index(), finished)

    async def run(self) -> AsyncIterator[bytes]:
        """Drive the stream; yields WAV chunks for the audio output."""
        s = self.session
        self._go(State.CONNECTING)
        url = self.settings.service_url
        pending: list[bytes] = []
        pending_ms = 0.0
        try:
            async for event in stream_speech(url, self.text, voice=self.voice, engine=self.engine):
                if isinstance(event, Started):
                    s.request_id = event.request_id
                    self.sample_rate, self.channels = event.sample_rate, event.channels
                    s.engine, s.voice = event.engine, event.voice
                    log.info("request=%s engine=%s voice=%s", s.request_id, s.engine, s.voice)
                    self._go(State.PLAYING)
                elif isinstance(event, AudioChunk):
                    s.audio_ms_received += event.ms
                    pending.append(event.payload)
                    pending_ms += event.ms
                    threshold = self.settings.prebuffer_ms if self.t0 is None else 0
                    if pending_ms < max(threshold, self.settings.chunk_ms):
                        continue  # fewer, larger pieces keep Gradio's per-chunk cost low
                    if self.t0 is None:
                        self.t0 = time.monotonic()
                    yield pcm_to_wav_chunk(b"".join(pending), self.sample_rate, self.channels)
                    pending.clear()
                    pending_ms = 0.0
                elif isinstance(event, Completed):
                    if pending:  # audio ended before a full piece accumulated
                        if self.t0 is None:
                            self.t0 = time.monotonic()
                        yield pcm_to_wav_chunk(b"".join(pending), self.sample_rate, self.channels)
                        pending.clear()
                        pending_ms = 0.0
                    s.total_audio_ms = event.audio_ms
                    self.timeline.rescale(event.audio_ms / 1000)
                elif isinstance(event, ServiceError):
                    self.error_code = event.code
                    self.fail(errors.message_for(event.code, limit=self.settings.max_text_chars))
        except ServiceUnreachable:
            self.fail(errors.unreachable(url))
        except UnsupportedStream:
            self.fail("The service uses an audio format this demo can't play.")
