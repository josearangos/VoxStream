"""PCM to WAV helpers for Gradio's streaming audio output."""

from __future__ import annotations

import io
import wave

SAMPLE_WIDTH = 2  # pcm_s16le


def pcm_to_wav_chunk(payload: bytes, sample_rate: int, channels: int) -> bytes:
    """Wrap raw ``pcm_s16le`` bytes in a WAV header."""
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(channels)
        w.setsampwidth(SAMPLE_WIDTH)
        w.setframerate(sample_rate)
        w.writeframes(payload)
    return buf.getvalue()


def payload_ms(payload: bytes, sample_rate: int, channels: int) -> float:
    return len(payload) / (SAMPLE_WIDTH * channels * sample_rate) * 1000
