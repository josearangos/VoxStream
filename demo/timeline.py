"""Estimated word timeline: no word timing exists in protocol v1 (research R3)."""

from __future__ import annotations

import re
from bisect import bisect_right
from dataclasses import dataclass, replace

_WORD = re.compile(r"\S+")
_SENTENCE_END = ".!?…"
_CLOSERS = "\"'»”’)]"


@dataclass(frozen=True)
class TimelineWord:
    index: int
    text: str
    char_start: int
    char_end: int
    weight: int
    start_s: float
    end_s: float


class Timeline:
    def __init__(self, words: list[TimelineWord]) -> None:
        self.words = words

    def __len__(self) -> int:
        return len(self.words)

    @property
    def total_s(self) -> float:
        return self.words[-1].end_s if self.words else 0.0

    def rescale(self, total_audio_s: float) -> None:
        """Scale every time by one factor so the last word ends at the audio end."""
        if not self.words or self.total_s <= 0 or total_audio_s <= 0:
            return
        k = total_audio_s / self.total_s
        self.words = [replace(w, start_s=w.start_s * k, end_s=w.end_s * k) for w in self.words]

    def word_at(self, seconds: float) -> int:
        """Index of the word being spoken at ``seconds``, clamped to first/last (-1 if empty)."""
        if not self.words:
            return -1
        i = bisect_right([w.start_s for w in self.words], seconds) - 1
        return max(0, min(i, len(self.words) - 1))

    def reanchor(self, now_s: float, word_index: int) -> None:
        """Shift ``word_index`` and all later words so that word starts at ``now_s``."""
        if not 0 <= word_index < len(self.words):
            return
        if word_index > 0:
            now_s = max(now_s, self.words[word_index - 1].end_s)
        delta = now_s - self.words[word_index].start_s
        self.words[word_index:] = [
            replace(w, start_s=w.start_s + delta, end_s=w.end_s + delta)
            for w in self.words[word_index:]
        ]


def build_timeline(
    text: str,
    chars_per_s: float,
    *,
    pause_comma: int = 3,
    pause_sentence: int = 6,
    pause_linebreak: int = 8,
) -> Timeline:
    matches = list(_WORD.finditer(text))
    words: list[TimelineWord] = []
    t = 0.0
    for i, m in enumerate(matches):
        token = m.group()
        core = token.rstrip(_CLOSERS)
        weight = len(token)
        if core.endswith(","):
            weight += pause_comma
        elif core and core[-1] in _SENTENCE_END + ":;":
            weight += pause_sentence
        nxt = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        if "\n" in text[m.end() : nxt]:
            weight += pause_linebreak
        dur = weight / chars_per_s
        words.append(TimelineWord(i, token, m.start(), m.end(), weight, t, t + dur))
        t += dur
    return Timeline(words)
