"""Spanish voice candidates and the verification gate (research R-08)."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

CANDIDATE_VOICES: tuple[str, ...] = ("ef_dora", "em_alex", "em_santa")
LANGUAGE = "es"


@dataclass
class VoiceGate:
    voices: list[str] = field(default_factory=list)
    reason: str | None = None  # why nothing is exposed, when voices is empty
    warnings: list[str] = field(default_factory=list)


def load_gate(verification_file: Path, model_sha256: str | None) -> VoiceGate:
    """Expose a voice only if its automated check passed for the installed model checksum."""
    if model_sha256 is None:
        return VoiceGate(reason="Model file is missing; run 'voxstream download-models'.")
    if not verification_file.exists():
        return VoiceGate(
            reason="No voice verification result found; run 'voxstream verify-voices'."
        )
    try:
        data: dict[str, Any] = json.loads(verification_file.read_text())
        recorded = data["model"]["sha256"]
        results: dict[str, Any] = data["voices"]
    except (OSError, ValueError, KeyError, TypeError):
        return VoiceGate(
            reason="Voice verification result is unreadable; rerun 'voxstream verify-voices'."
        )
    if recorded != model_sha256:
        return VoiceGate(
            reason="Voice verification was made for a different model file; "
            "rerun 'voxstream verify-voices'."
        )
    gate = VoiceGate()
    for voice, res in results.items():
        if not isinstance(res, dict) or res.get("passed") is not True:
            continue
        gate.voices.append(voice)
        if not res.get("manual_signoff"):
            gate.warnings.append(
                f"Voice {voice!r} has no manual listening sign-off "
                f"(voxstream verify-voices --signoff {voice})."
            )
    if not gate.voices:
        gate.reason = "No Spanish voice passed verification; a different model may be needed."
    return gate
