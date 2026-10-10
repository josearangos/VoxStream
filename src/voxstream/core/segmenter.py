"""Incremental Spanish text segmenter (research R-06)."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal

Reason = Literal["sentence_end", "fallback_length", "end_of_text"]

ABBREVIATIONS = frozenset(
    {
        "sr", "sra", "srta", "dr", "dra", "etc", "pág", "págs", "ud", "uds", "vd", "vds",
        "av", "avda", "núm", "prof", "lic", "ing", "sta", "sto", "aprox", "tel", "cap",
        "art", "ej", "vs", "mr", "mrs", "pp", "ee", "uu",
    }
)  # fmt: skip

_IMMEDIATE = "!?…;"
_CLOSERS = "\"'»”’)]"
_WORD_BEFORE = re.compile(r"([^\W\d_]+)$")
_HAS_SPEECH = re.compile(r"\w")


@dataclass(frozen=True)
class Segment:
    index: int
    text: str
    reason: Reason


class Segmenter:
    def __init__(self, max_pending_chars: int = 120) -> None:
        self.max_pending_chars = max_pending_chars
        self._buf = ""
        self._carry = ""
        self._count = 0

    @property
    def count(self) -> int:
        return self._count

    def push(self, text: str) -> list[Segment]:
        self._buf += text
        return self._drain(final=False)

    def flush(self) -> list[Segment]:
        return self._drain(final=True)

    def _drain(self, final: bool) -> list[Segment]:
        out: list[Segment] = []
        while True:
            found = self._find_cut(final)
            if found is None:
                break
            cut, reason = found
            raw, self._buf = self._buf[:cut], self._buf[cut:]
            text = " ".join((self._carry + " " + raw).split())
            if not _HAS_SPEECH.search(text):
                self._carry = text  # punctuation only: attach to the next segment
                continue
            self._carry = ""
            out.append(Segment(self._count, text, reason))
            self._count += 1
        if final:
            self._buf = ""
            self._carry = ""
        return out

    def _find_cut(self, final: bool) -> tuple[int, Reason] | None:
        buf = self._buf
        if not buf.strip():
            return None
        limit = self.max_pending_chars
        sentence = self._sentence_cut(buf, final)
        if sentence is not None and sentence <= limit:
            return sentence, "sentence_end"
        if len(buf) >= limit:
            cut = self._fallback_cut(buf, limit)
            if cut is not None:
                return cut, "fallback_length"
        if sentence is not None:
            return sentence, "sentence_end"
        if final:
            return len(buf), "end_of_text"
        return None

    @staticmethod
    def _fallback_cut(buf: str, limit: int) -> int | None:
        head = buf[:limit]
        comma = head.rfind(",")
        pos = comma if comma >= limit // 2 else max(comma, head.rfind(" "))  # prefer a late comma
        if pos > 0:
            return pos + 1
        for i in range(limit, len(buf)):
            if buf[i] in ", ":
                return i + 1
        return None

    @staticmethod
    def _sentence_cut(buf: str, final: bool) -> int | None:
        n = len(buf)
        i = 0
        while i < n:
            ch = buf[i]
            if ch == "\n":
                return i + 1
            if ch in _IMMEDIATE:
                j = i + 1
                while j < n and buf[j] in _IMMEDIATE + ".":
                    j += 1
                while j < n and buf[j] in _CLOSERS:
                    j += 1
                return j
            if ch == ".":
                j = i
                while j < n and buf[j] == ".":
                    j += 1
                k = j
                while k < n and buf[k] in _CLOSERS:
                    k += 1
                if k == n:
                    return n if final else None  # wait: "3." may become "3.5"
                if buf[k].isspace():
                    if j - i == 1 and Segmenter._is_abbreviation(buf[:i]):
                        i = k
                        continue
                    return k
                i = j
                continue
            i += 1
        return None

    @staticmethod
    def _is_abbreviation(before: str) -> bool:
        m = _WORD_BEFORE.search(before)
        if not m:
            return False
        word = m.group(1)
        if len(word) == 1 and word.isupper():
            return True  # initials: "J. K. Rowling"
        return word.lower() in ABBREVIATIONS
