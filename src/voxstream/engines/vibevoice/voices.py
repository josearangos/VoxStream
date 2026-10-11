"""Spanish voice candidates for VibeVoice-Realtime-0.5B (research R-09).

These are the experimental Spanish presets from ``experimental_voices_sp.tar.gz``. The model card
says they are "not extensively tested"; the verification gate decides which are exposed.
"""

from __future__ import annotations

CANDIDATE_VOICES: tuple[str, ...] = (
    "sp-Spk2_woman",
    "sp-Spk3_man",
    "sp-Spk4_woman",
    "sp-Spk5_man",
)
LANGUAGE = "es"
SAMPLE_RATE = 24000
