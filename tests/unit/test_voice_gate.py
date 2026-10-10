import json

from voxstream.config import Settings
from voxstream.engines.kokoro.engine import KokoroEngine
from voxstream.engines.kokoro.voices import load_gate


def write(path, sha="sha1", voices=None):
    voices = voices or {
        "ef_dora": {"passed": True, "manual_signoff": {"by": "me", "date": "2026-01-01"}},
        "em_alex": {"passed": False, "manual_signoff": None},
        "em_santa": {"passed": True, "manual_signoff": None},
    }
    path.write_text(json.dumps({"model": {"name": "k", "sha256": sha}, "voices": voices}))


def test_only_passed_voices_with_matching_checksum(tmp_path):
    f = tmp_path / "v.json"
    write(f)
    gate = load_gate(f, "sha1")
    assert gate.voices == ["ef_dora", "em_santa"]
    assert len(gate.warnings) == 1 and "em_santa" in gate.warnings[0]  # no sign-off: warn only


def test_checksum_mismatch_hides_everything(tmp_path):
    f = tmp_path / "v.json"
    write(f, sha="old")
    gate = load_gate(f, "new")
    assert gate.voices == [] and "different model" in gate.reason


def test_missing_file_or_model_hides_everything(tmp_path):
    assert load_gate(tmp_path / "none.json", "sha1").voices == []
    f = tmp_path / "v.json"
    write(f)
    assert load_gate(f, None).voices == []


def test_corrupt_file_hides_everything(tmp_path):
    f = tmp_path / "v.json"
    f.write_text("{not json")
    assert load_gate(f, "sha1").voices == []


def test_no_passing_voice_is_not_ready(tmp_path):
    models = tmp_path / "models"
    models.mkdir()
    (models / "kokoro-v1.0.onnx").write_bytes(b"model")
    (models / "voices-v1.0.bin").write_bytes(b"v")
    s = Settings(
        _env_file=None, models_dir=str(models), verification_file=str(tmp_path / "missing.json")
    )
    ok, reason, _ = KokoroEngine(s).readiness()
    assert not ok and "verify-voices" in reason
    assert KokoroEngine(s).capabilities().voices == []
