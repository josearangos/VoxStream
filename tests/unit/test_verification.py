import numpy as np
import pytest

from voxstream.verification import spanish as sp

SENTENCES = ["El niño comió 25 manzanas.", "¿Dónde está la Sra. García?"]


def fake_synth(text, voice):
    return np.zeros(2400, dtype=np.int16)


def test_normalize_case_punct_accents():
    assert sp.normalize("¡Mañana, NIÑO! ¿Cómo?") == "manana nino como"


def test_normalize_numbers_and_abbreviations():
    assert sp.normalize("Tengo 25 años") == "tengo veinticinco anos"
    assert sp.normalize("1.000 pesos") == "mil pesos"
    assert sp.normalize("La Sra. García") == sp.normalize("La señora García")
    assert sp.normalize("150") == "ciento cincuenta"


def test_wer_ignores_accent_and_case():
    assert sp.default_wer("El niño comió", "el nino comio") == 0.0
    assert sp.default_wer("uno dos tres cuatro", "uno dos tres") == pytest.approx(0.25)


def run(transcripts_by_voice, mean=0.15, mx=0.35):
    def transcribe_for(voice):
        it = iter(transcripts_by_voice[voice])
        return lambda pcm: next(it)

    out = {}
    for voice in transcripts_by_voice:
        out.update(
            sp.evaluate_voices(
                [voice],
                SENTENCES,
                fake_synth,
                transcribe_for(voice),
                mean_threshold=mean,
                max_threshold=mx,
            )
        )
    return out


def test_pass_rule():
    res = run(
        {
            "good": ["el nino comio veinticinco manzanas", "donde esta la señora garcia"],
            "bad": ["xxx yyy zzz", "donde esta la señora garcia"],
            "edge": ["el nino comio veinticinco manzanas", "donde esta la señora"],  # 0.25 sentence
        }
    )
    assert res["good"]["passed"] and res["good"]["mean_wer"] == 0
    assert not res["bad"]["passed"]
    assert res["edge"]["passed"]  # mean 0.125 <= 0.15 and max 0.2 <= 0.35


def test_mean_and_max_thresholds_independent():
    res = run({"v": ["el nino comio veinticinco manzanas", "donde esta"]}, mean=0.5, mx=0.35)
    assert res["v"]["max_sentence_wer"] > 0.35 and not res["v"]["passed"]


def test_json_shape():
    res = run({"v": ["el nino comio veinticinco manzanas", "donde esta la señora garcia"]})
    final = sp.build_result(
        res, model_sha256="abc", recognizer="fake", mean_threshold=0.15, max_threshold=0.35
    )
    assert set(final) == {"model", "recognizer", "threshold", "voices", "generated_at"}
    assert final["model"] == {"name": "kokoro-v1.0", "sha256": "abc"}
    v = final["voices"]["v"]
    assert set(v) == {"mean_wer", "max_sentence_wer", "passed", "sentences", "manual_signoff"}
    assert set(v["sentences"][0]) == {"reference", "transcript", "wer"}
    assert v["manual_signoff"] is None


def test_signoff_requires_pass_and_is_kept_for_same_model():
    res = run({"v": ["xx", "yy"]})
    final = sp.build_result(
        res, model_sha256="a", recognizer="r", mean_threshold=0.15, max_threshold=0.35
    )
    with pytest.raises(ValueError):
        sp.record_signoff(final, "v", "me")
    good = run({"v": ["el nino comio veinticinco manzanas", "donde esta la señora garcia"]})
    final = sp.build_result(
        good, model_sha256="a", recognizer="r", mean_threshold=0.15, max_threshold=0.35
    )
    sp.record_signoff(final, "v", "me")
    again = run({"v": ["el nino comio veinticinco manzanas", "donde esta la señora garcia"]})
    kept = sp.build_result(
        again,
        model_sha256="a",
        recognizer="r",
        mean_threshold=0.15,
        max_threshold=0.35,
        previous=final,
    )
    assert kept["voices"]["v"]["manual_signoff"]["by"] == "me"
    again = run({"v": ["el nino comio veinticinco manzanas", "donde esta la señora garcia"]})
    other = sp.build_result(
        again,
        model_sha256="b",
        recognizer="r",
        mean_threshold=0.15,
        max_threshold=0.35,
        previous=final,
    )
    assert other["voices"]["v"]["manual_signoff"] is None
