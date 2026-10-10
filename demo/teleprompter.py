"""Render the teleprompter panel as escaped HTML."""

from __future__ import annotations

from html import escape

from demo.timeline import TimelineWord

CURRENT_ID = "tp-current"


def render(text: str, words: list[TimelineWord], current_index: int, finished: bool) -> str:
    """Words before ``current_index`` are spoken, at it current, after it upcoming."""
    parts: list[str] = []
    pos = 0
    for w in words:
        parts.append(escape(text[pos : w.char_start]))
        if finished or w.index < current_index:
            cls, attr = "spoken", ""
        elif w.index == current_index:
            cls, attr = "current", f' id="{CURRENT_ID}"'
        else:
            cls, attr = "upcoming", ""
        parts.append(f'<span class="{cls}"{attr}>{escape(w.text)}</span>')
        pos = w.char_end
    parts.append(escape(text[pos:]))
    style = "white-space: pre-wrap; position: relative; max-height: 22em; overflow-y: auto"
    return f'<div class="teleprompter" style="{style}">{"".join(parts)}</div>'
