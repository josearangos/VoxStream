"""Spanish voice candidates for Kokoro; the verification gate is shared (research R-08)."""

from __future__ import annotations

from voxstream.engines.voice_gate import VoiceGate, load_gate

__all__ = ["CANDIDATE_VOICES", "LANGUAGE", "VoiceGate", "load_gate"]

CANDIDATE_VOICES: tuple[str, ...] = ("ef_dora", "em_alex", "em_santa")
LANGUAGE = "es"
