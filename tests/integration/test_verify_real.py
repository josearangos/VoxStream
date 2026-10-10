import json

import pytest

from voxstream.config import Settings
from voxstream.verification import spanish as sp

pytestmark = pytest.mark.model


def test_real_verification_produces_result_file(tmp_path):
    out = tmp_path / "result.json"
    settings = Settings(_env_file=None, verification_file=str(out))
    rc = sp.run_cli(settings, ["ef_dora"], None, None)
    assert out.exists()
    data = json.loads(out.read_text())
    assert "ef_dora" in data["voices"] and data["model"]["sha256"]
    assert rc in (0, 1)
