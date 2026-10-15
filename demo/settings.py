"""Demo settings, read from ``DEMO_*`` environment variables."""

from __future__ import annotations

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

LOOPBACK_HOSTS = ("127.0.0.1", "localhost", "::1")


class DemoSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="DEMO_", extra="ignore")

    service_url: str = "ws://127.0.0.1:8765/v1/stream"
    host: str = "127.0.0.1"
    port: int = 7860
    playback_lead_ms: int = 0
    chunk_ms: int = 800  # coalesce service chunks into WAV pieces of at least this length
    prebuffer_ms: int = 0  # hold this much audio before playing (for engines slower than real time)
    max_text_chars: int = 2000
    speech_rate_chars_per_s: float = 14.0
    pause_weight_comma: int = 3
    pause_weight_sentence: int = 6
    pause_weight_linebreak: int = 8

    @field_validator("host")
    @classmethod
    def _loopback_only(cls, v: str) -> str:
        if v not in LOOPBACK_HOSTS:
            raise ValueError(f"Refusing to bind the demo to {v!r}; it is localhost-only")
        return v
