"""Gradio teleprompter demo: a localhost-only client of the VoxStream WebSocket service."""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from typing import Any

import gradio as gr

from demo import errors
from demo.playback import Runtime
from demo.service_info import (
    KNOWN_ENGINES,
    SERVICE_DEFAULT_VOICE,
    UNKNOWN,
    ServiceInfo,
    display_name,
    fetch_service_info,
    info_line,
    other_engines,
    restart_hint,
    voice_choices,
)
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

REFRESH_CODES = frozenset({"ENGINE_UNAVAILABLE", "UNSUPPORTED_ENGINE", "UNSUPPORTED_VOICE"})

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
    """status, teleprompter, start, stop, timer, refresh, voice (locked while active)"""
    start, stop, timer = _controls(rt)
    refresh = gr.update(interactive=not rt.active)
    voice = gr.update(interactive=not rt.active and rt.voice is not None)
    return rt.status(), rt.html(), start, stop, timer, refresh, voice


def _speaking(rt: Runtime) -> str:
    s = rt.session
    if s.engine is None and s.voice is None:
        return ""
    return f"Speaking with {display_name(s.engine)} · {s.voice or SERVICE_DEFAULT_VOICE}"


def _info_view(info: ServiceInfo) -> tuple[Any, ...]:
    """info line, engine radio, hint, voice dropdown for a ServiceInfo."""
    choices, selected = voice_choices(info)
    hint = " ".join(restart_hint(o, info.engine) for o in other_engines(info.engine))
    return (
        info_line(info),
        gr.update(value=display_name(info.engine) if info.engine in KNOWN_ENGINES else None),
        hint if info.engine in KNOWN_ENGINES else "",
        gr.update(
            choices=choices or [SERVICE_DEFAULT_VOICE],
            value=selected or SERVICE_DEFAULT_VOICE,
            interactive=bool(choices),
        ),
    )


def build_app(settings: DemoSettings) -> gr.Blocks:
    with gr.Blocks(title="VoxStream Teleprompter") as demo:
        gr.Markdown("# VoxStream Teleprompter\nType Spanish text, press Start, and follow along.")
        text = gr.Textbox(label="Text", value=SAMPLE_TEXT, lines=6, max_lines=12, interactive=True)
        with gr.Row():
            start_btn = gr.Button("Start", variant="primary")
            stop_btn = gr.Button("Stop", interactive=False)
        info_md = gr.Markdown("")
        engine_radio = gr.Radio(
            [display_name(e) for e in KNOWN_ENGINES], label="Engine", interactive=False
        )
        hint_md = gr.Markdown("")
        with gr.Row():
            voice_dd = gr.Dropdown(
                [SERVICE_DEFAULT_VOICE], value=SERVICE_DEFAULT_VOICE, label="Voice",
                interactive=False,
            )  # fmt: skip
            refresh_btn = gr.Button("Refresh")
        speaking = gr.Markdown("")
        info_state = gr.State(UNKNOWN)
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

        outs = [status, panel, start_btn, stop_btn, timer, refresh_btn, voice_dd]
        info_outs = [info_state, info_md, engine_radio, hint_md, voice_dd]
        start_info_outs = info_outs[:-1]  # voice_dd is already in `outs`

        async def load_info() -> tuple[Any, ...]:
            info = await fetch_service_info(settings.service_url)
            return (info, *_info_view(info))

        async def on_refresh(request: gr.Request) -> tuple[Any, ...]:
            old = _RUNTIMES.get(request.session_hash or "")
            if old is not None:
                old.stop()
            return await load_info()

        async def on_start(
            txt: str, voice: str | None, info: ServiceInfo, request: gr.Request
        ) -> AsyncIterator[tuple[Any, ...]]:
            sid = request.session_hash or ""
            skip = gr.skip()
            no_info = tuple(skip for _ in start_info_outs)
            if not (txt or "").strip():
                yield skip, errors.EMPTY_INPUT, *(skip,) * 6, skip, *no_info
                return
            if len(txt) > settings.max_text_chars:
                yield skip, errors.too_long(settings.max_text_chars), *(skip,) * 6, skip, *no_info
                return
            old = _RUNTIMES.get(sid)
            if old is not None:
                old.stop()  # Start while active stops the previous playback first
            chosen = voice if info.voices and voice in info.voices else None
            rt = Runtime(settings, txt, voice=chosen, engine=info.engine)
            _RUNTIMES[sid] = rt
            yield (skip, *_view(rt), "", *no_info)
            try:
                first = True
                async for wav in rt.run():
                    # Only the first chunk carries a full UI update; the 5 Hz timer keeps status
                    # and teleprompter fresh. Later chunks send audio alone so a burst of fast
                    # engine output (Kokoro) doesn't flood the websocket with re-renders.
                    if first:
                        first = False
                        yield (wav, *_view(rt), _speaking(rt), *no_info)
                    else:
                        yield (wav, *(skip,) * 8, *no_info)
            finally:
                if rt.session.total_audio_ms is None:
                    rt.stop()  # Stop/disconnect before completion; else the timer finishes it
            view = list(_view(rt))
            refreshed = no_info
            if rt.session.error and rt.error_code in REFRESH_CODES:
                *refreshed, view[-1] = (await load_info())[:5]  # type: ignore[assignment]
            yield (skip, *view, _speaking(rt), *refreshed)

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
            *main, refresh, voice = _view(rt)
            if rt.active:  # locks only change at start/stop; keep the 5 Hz tick light
                refresh = voice = gr.skip()
            return (*main, refresh, voice)

        start_event = start_btn.click(
            on_start,
            [text, voice_dd, info_state],
            [audio, *outs, speaking, *start_info_outs],
            trigger_mode="once",
            show_progress="hidden",
        )
        stop_btn.click(on_stop, None, outs, cancels=[start_event], js=STOP_AUDIO_JS)
        timer.tick(on_tick, None, outs, show_progress="hidden")
        refresh_btn.click(on_refresh, None, info_outs, cancels=[start_event], js=STOP_AUDIO_JS)
        demo.load(load_info, None, info_outs)
    return demo  # type: ignore[no-any-return]


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(message)s")
    settings = DemoSettings()
    build_app(settings).queue().launch(
        server_name=settings.host, server_port=settings.port, share=False, css=CSS
    )


if __name__ == "__main__":
    main()
