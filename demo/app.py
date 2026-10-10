"""Gradio teleprompter demo: a localhost-only client of the VoxStream WebSocket service."""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from typing import Any

import gradio as gr

from demo import errors
from demo.playback import Runtime
from demo.session import State
from demo.settings import DemoSettings

SAMPLE_TEXT = (
    "Hola, bienvenido a VoxStream. Esta es una demostración de síntesis de voz en tiempo real.\n"
    "Mientras escuchas el audio, las palabras se resaltan para que puedas seguir el texto "
    "como en un teleprompter. ¿Te gusta cómo suena?"
)
AUTOPLAY_HINT = "Your browser blocked audio. Click the player's play button."
CSS = """
.teleprompter { font-size: 1.25rem; line-height: 1.8; padding: .75rem; }
.teleprompter .spoken { opacity: .4; }
.teleprompter .current { background: #fde68a; color: #111; border-radius: 4px; padding: 0 2px; }
"""
AUTOSCROLL_JS = """
const scroll = () => {
  const box = element.querySelector('.teleprompter');
  const cur = element.querySelector('#tp-current');
  if (box && cur) box.scrollTop = cur.offsetTop - box.clientHeight / 2;
};
watch('value', scroll);
"""
STOP_AUDIO_JS = "() => { document.querySelectorAll('audio').forEach(a => a.pause()); }"

log = logging.getLogger("demo")

# One runtime per browser session (keyed by Gradio session hash).
_RUNTIMES: dict[str, Runtime] = {}


def _controls(rt: Runtime) -> tuple[Any, Any, Any]:
    """Start button, Stop button, timer updates for the runtime's current state."""
    return (
        gr.update(interactive=not rt.active),
        gr.update(interactive=rt.active),
        gr.Timer(active=rt.active or rt.session.state is State.PLAYING),
    )


def _view(rt: Runtime) -> tuple[Any, ...]:
    """status, teleprompter, start, stop, timer"""
    start, stop, timer = _controls(rt)
    return rt.status(), rt.html(), start, stop, timer


def build_app(settings: DemoSettings) -> gr.Blocks:
    with gr.Blocks(title="VoxStream Teleprompter") as demo:
        gr.Markdown("# VoxStream Teleprompter\nType Spanish text, press Start, and follow along.")
        text = gr.Textbox(label="Text", value=SAMPLE_TEXT, lines=6, max_lines=12, interactive=True)
        with gr.Row():
            start_btn = gr.Button("Start", variant="primary")
            stop_btn = gr.Button("Stop", interactive=False)
        status = gr.Textbox(label="Status", value="Ready", interactive=False)
        audio = gr.Audio(
            label="Audio",
            streaming=True,
            autoplay=True,
            interactive=False,
            buttons=[],
            format="wav",
        )
        gr.Markdown(f"_{AUTOPLAY_HINT} (shown only if the browser stops playback)_")
        panel = gr.HTML(value="", js_on_load=AUTOSCROLL_JS, label="Teleprompter")
        timer = gr.Timer(0.2, active=False)

        outs = [status, panel, start_btn, stop_btn, timer]

        async def on_start(txt: str, request: gr.Request) -> AsyncIterator[tuple[Any, ...]]:
            sid = request.session_hash or ""
            skip = gr.skip()
            if not (txt or "").strip():
                yield skip, errors.EMPTY_INPUT, skip, skip, skip, skip
                return
            if len(txt) > settings.max_text_chars:
                yield skip, errors.too_long(settings.max_text_chars), skip, skip, skip, skip
                return
            old = _RUNTIMES.get(sid)
            if old is not None:
                old.stop()  # Start while active stops the previous playback first
            rt = Runtime(settings, txt)
            _RUNTIMES[sid] = rt
            yield (skip, *_view(rt))
            try:
                async for wav in rt.run():
                    yield (wav, *_view(rt))
            finally:
                if rt.session.total_audio_ms is None:
                    rt.stop()  # Stop/disconnect before completion; else the timer finishes it
            yield (skip, *_view(rt))

        def on_stop(request: gr.Request) -> tuple[Any, ...]:
            rt = _RUNTIMES.get(request.session_hash or "")
            if rt is None:
                return tuple(gr.skip() for _ in outs)
            rt.stop()
            return _view(rt)

        def on_tick(request: gr.Request) -> tuple[Any, ...]:
            rt = _RUNTIMES.get(request.session_hash or "")
            if rt is None:
                return tuple(gr.skip() for _ in outs)
            rt.tick()
            return _view(rt)

        start_event = start_btn.click(
            on_start, [text], [audio, *outs], trigger_mode="once", show_progress="hidden"
        )
        stop_btn.click(on_stop, None, outs, cancels=[start_event], js=STOP_AUDIO_JS)
        timer.tick(on_tick, None, outs, show_progress="hidden")
    return demo  # type: ignore[no-any-return]


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(message)s")
    settings = DemoSettings()
    build_app(settings).queue().launch(
        server_name=settings.host, server_port=settings.port, share=False, css=CSS
    )


if __name__ == "__main__":
    main()
