"""TorchBackend error branches that must work without torch installed (G1)."""

import sys
from pathlib import Path

import pytest

from voxstream.cli import VIBEVOICE_VOICE_SHA256
from voxstream.engines.base import EngineUnavailableError
from voxstream.engines.vibevoice.backend import TorchBackend
from voxstream.engines.vibevoice.voices import CANDIDATE_VOICES


def test_unknown_device_is_actionable():
    with pytest.raises(EngineUnavailableError, match="Unknown VibeVoice device 'cuda'"):
        TorchBackend(Path("none"), "cuda").load()


def test_missing_dependencies_name_the_extra(monkeypatch):
    monkeypatch.setitem(sys.modules, "torch", None)  # makes "import torch" raise ImportError
    with pytest.raises(EngineUnavailableError, match="uv sync --extra vibevoice"):
        TorchBackend(Path("none"), "cpu").load()


def test_unavailable_mps_is_an_error_not_a_fallback(monkeypatch):
    torch = pytest.importorskip("torch")
    pytest.importorskip("vibevoice")
    monkeypatch.setattr(torch.backends.mps, "is_available", lambda: False)
    with pytest.raises(EngineUnavailableError, match="not available.*Not switching silently"):
        TorchBackend(Path("none"), "mps").load()


def test_every_candidate_voice_has_a_pinned_checksum():
    assert set(VIBEVOICE_VOICE_SHA256) == set(CANDIDATE_VOICES)
    assert all(len(v) == 64 for v in VIBEVOICE_VOICE_SHA256.values())
