"""Transcribe-and-compare check that Kokoro voices produce intelligible Spanish (R-08).

``faster-whisper`` and ``jiwer`` are imported lazily here only; serving never needs them.
"""

from __future__ import annotations

import asyncio
import datetime
import getpass
import json
import re
import unicodedata
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any

import numpy as np
import numpy.typing as npt

from voxstream.config import Settings

SynthFn = Callable[[str, str], npt.NDArray[np.int16]]  # (text, voice) -> 24 kHz mono PCM
TranscribeFn = Callable[[npt.NDArray[np.int16]], str]
WerFn = Callable[[str, str], float]

REFERENCE_FILE = Path("verification/reference_sentences_es.txt")

_UNITS = (
    "cero uno dos tres cuatro cinco seis siete ocho nueve diez once doce trece catorce quince "
    "dieciséis diecisiete dieciocho diecinueve veinte veintiuno veintidós veintitrés "
    "veinticuatro veinticinco veintiséis veintisiete veintiocho veintinueve"
).split()
_TENS = {3: "treinta", 4: "cuarenta", 5: "cincuenta", 6: "sesenta", 7: "setenta", 8: "ochenta",
         9: "noventa"}  # fmt: skip
_HUNDREDS = ["", "ciento", "doscientos", "trescientos", "cuatrocientos", "quinientos",
             "seiscientos", "setecientos", "ochocientos", "novecientos"]  # fmt: skip
_ABBREVIATIONS = {"sr": "señor", "sra": "señora", "srta": "señorita", "dr": "doctor",
                  "dra": "doctora", "etc": "etcétera"}  # fmt: skip


def number_words(n: int) -> str:
    if n < 30:
        return _UNITS[n]
    if n < 100:
        tens, unit = divmod(n, 10)
        return _TENS[tens] + (f" y {_UNITS[unit]}" if unit else "")
    if n < 1000:
        if n == 100:
            return "cien"
        h, rest = divmod(n, 100)
        return _HUNDREDS[h] + (f" {number_words(rest)}" if rest else "")
    if n < 1_000_000:
        k, rest = divmod(n, 1000)
        head = "mil" if k == 1 else f"{number_words(k)} mil"
        return head + (f" {number_words(rest)}" if rest else "")
    return str(n)


def normalize(text: str) -> str:
    """Case, punctuation and accents folded; digits and common abbreviations spelled out."""
    text = re.sub(r"(?<=\d)\.(?=\d{3}\b)", "", text)
    text = re.sub(r"\d+", lambda m: f" {number_words(int(m.group()))} ", text)
    text = re.sub(
        r"\b(" + "|".join(_ABBREVIATIONS) + r")\b\.?",
        lambda m: _ABBREVIATIONS[m.group(1).lower()],
        text,
        flags=re.IGNORECASE,
    )
    text = unicodedata.normalize("NFKD", text.lower())
    text = "".join(c for c in text if not unicodedata.combining(c))
    text = re.sub(r"[^a-z0-9ñ\s]", " ", text.replace("ñ", "n"))
    return " ".join(text.split())


def default_wer(reference: str, hypothesis: str) -> float:
    import jiwer

    return float(jiwer.wer(normalize(reference), normalize(hypothesis) or "<empty>"))


def evaluate_voices(
    voices: Sequence[str],
    sentences: Sequence[str],
    synth: SynthFn,
    transcribe: TranscribeFn,
    *,
    mean_threshold: float,
    max_threshold: float,
    wer: WerFn = default_wer,
) -> dict[str, dict[str, Any]]:
    results: dict[str, dict[str, Any]] = {}
    for voice in voices:
        rows: list[dict[str, Any]] = []
        for sentence in sentences:
            transcript = transcribe(synth(sentence, voice))
            rows.append(
                {
                    "reference": sentence,
                    "transcript": transcript,
                    "wer": round(wer(sentence, transcript), 4),
                }
            )
        scores = [r["wer"] for r in rows]
        mean, worst = sum(scores) / len(scores), max(scores)
        results[voice] = {
            "mean_wer": round(mean, 4),
            "max_sentence_wer": round(worst, 4),
            "passed": mean <= mean_threshold and worst <= max_threshold,
            "sentences": rows,
            "manual_signoff": None,
        }
    return results


def build_result(
    voice_results: dict[str, dict[str, Any]],
    *,
    model_sha256: str,
    recognizer: str,
    mean_threshold: float,
    max_threshold: float,
    previous: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if previous and previous.get("model", {}).get("sha256") == model_sha256:
        for voice, res in voice_results.items():
            old = previous.get("voices", {}).get(voice, {})
            if res["passed"] and old.get("manual_signoff"):
                res["manual_signoff"] = old["manual_signoff"]
    merged = dict(previous.get("voices", {})) if previous else {}
    if not previous or previous.get("model", {}).get("sha256") != model_sha256:
        merged = {}
    merged.update(voice_results)
    return {
        "model": {"name": "kokoro-v1.0", "sha256": model_sha256},
        "recognizer": {"name": recognizer, "language": "es"},
        "threshold": {"mean_wer": mean_threshold, "max_sentence_wer": max_threshold},
        "voices": merged,
        "generated_at": datetime.datetime.now(datetime.UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }


def record_signoff(result: dict[str, Any], voice: str, by: str) -> None:
    res = result.get("voices", {}).get(voice)
    if res is None or not res.get("passed"):
        raise ValueError(f"Voice {voice!r} has no passing verification result; verify it first.")
    res["manual_signoff"] = {"by": by, "date": datetime.date.today().isoformat()}


def load_sentences(path: Path = REFERENCE_FILE) -> list[str]:
    return [ln.strip() for ln in path.read_text().splitlines() if ln.strip()]


# -- real synthesizer / recognizer ------------------------------------------------------------


def _kokoro_synth(settings: Settings) -> SynthFn:
    from voxstream.engines.base import CancelToken
    from voxstream.engines.kokoro.engine import KokoroEngine

    engine = KokoroEngine(settings)
    loop = asyncio.new_event_loop()
    loop.run_until_complete(engine.start())

    def synth(text: str, voice: str) -> npt.NDArray[np.int16]:
        async def run() -> list[npt.NDArray[np.int16]]:
            return [b.samples async for b in engine.synthesize(text, voice, CancelToken())]

        return np.concatenate(loop.run_until_complete(run()))

    return synth


def _whisper_transcribe() -> tuple[TranscribeFn, str]:
    from faster_whisper import WhisperModel
    from scipy.signal import resample_poly

    model = WhisperModel("small", device="cpu", compute_type="int8")

    def transcribe(pcm: npt.NDArray[np.int16]) -> str:
        audio = resample_poly(pcm.astype(np.float32) / 32768.0, 2, 3).astype(np.float32)  # 24k->16k
        segments, _ = model.transcribe(audio, language="es", beam_size=5)
        return " ".join(s.text.strip() for s in segments)

    return transcribe, "faster-whisper small"


def run_cli(
    settings: Settings, voices: list[str] | None, signoff: str | None, by: str | None
) -> int:
    from voxstream.engines.kokoro.engine import KokoroEngine
    from voxstream.engines.kokoro.voices import CANDIDATE_VOICES

    out = Path(settings.verification_file)
    previous: dict[str, Any] | None = json.loads(out.read_text()) if out.exists() else None
    if signoff:
        if previous is None:
            print("No verification result yet; run 'voxstream verify-voices' first.")
            return 1
        try:
            record_signoff(previous, signoff, by or getpass.getuser())
        except ValueError as exc:
            print(exc)
            return 1
        out.write_text(json.dumps(previous, ensure_ascii=False, indent=2) + "\n")
        print(f"Recorded sign-off for {signoff}.")
        return 0

    sha = KokoroEngine(settings).model_sha256()
    if sha is None:
        print("Model file not found; run 'voxstream download-models'.")
        return 1
    try:
        synth = _kokoro_synth(settings)
        transcribe, recognizer = _whisper_transcribe()
    except ImportError:
        print("Verification needs the 'verify' extra: uv sync --extra verify")
        return 1
    results = evaluate_voices(
        voices or list(CANDIDATE_VOICES),
        load_sentences(),
        synth,
        transcribe,
        mean_threshold=settings.verify_mean_wer,
        max_threshold=settings.verify_max_sentence_wer,
    )
    final = build_result(
        results,
        model_sha256=sha,
        recognizer=recognizer,
        mean_threshold=settings.verify_mean_wer,
        max_threshold=settings.verify_max_sentence_wer,
        previous=previous,
    )
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(final, ensure_ascii=False, indent=2) + "\n")
    for voice, res in results.items():
        status = "PASS" if res["passed"] else "FAIL"
        print(f"{voice}: {status} mean_wer={res['mean_wer']} max={res['max_sentence_wer']}")
    return 0 if any(r["passed"] for r in results.values()) else 1
