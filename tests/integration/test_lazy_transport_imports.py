import subprocess
import sys

import pytest

SCRIPT = """
import asyncio, sys
from voxstream.app import VoxStreamApp
from voxstream.config import Settings
from voxstream.engines.mock import MockEngine

async def main():
    s = Settings(_env_file=None, port=0, grpc_port=0, engine="mock",
                 enable_websocket={ws}, enable_grpc={grpc})
    async with VoxStreamApp(s, MockEngine()):
        pass
    loaded = {{m for m in sys.modules if m.startswith("voxstream.transports.")}}
    print(sorted(loaded))
    assert not any(m.startswith("{absent}") for m in sys.modules), "{absent} imported"

asyncio.run(main())
"""


@pytest.mark.parametrize(
    "ws,grpc,absent",
    [
        (True, False, "voxstream.transports.grpc"),
        (False, True, "voxstream.transports.websocket"),
    ],
)
def test_disabled_transport_is_never_imported(ws, grpc, absent):
    code = SCRIPT.format(ws=ws, grpc=grpc, absent=absent)
    r = subprocess.run(
        [sys.executable, "-I", "-c", code], capture_output=True, text=True, timeout=60
    )
    assert r.returncode == 0, r.stdout + r.stderr


def test_heavy_vibevoice_dependencies_are_never_imported_by_default():
    code = """
import sys
import voxstream, voxstream.app, voxstream.engines.registry as reg
from voxstream.config import Settings
reg.create_engine("mock", Settings(_env_file=None))
bad = [m for m in ("torch", "transformers", "vibevoice") if m in sys.modules]
assert not bad, bad
"""
    r = subprocess.run(
        [sys.executable, "-I", "-c", code], capture_output=True, text=True, timeout=60
    )
    assert r.returncode == 0, r.stdout + r.stderr


def test_creating_vibevoice_engine_does_not_import_torch():
    code = """
import sys
from voxstream.config import Settings
from voxstream.engines.registry import create_engine
create_engine("vibevoice", Settings(_env_file=None, engine="vibevoice"))
bad = [m for m in ("torch", "transformers", "vibevoice") if m in sys.modules]
assert not bad, bad
"""
    r = subprocess.run(
        [sys.executable, "-I", "-c", code], capture_output=True, text=True, timeout=60
    )
    assert r.returncode == 0, r.stdout + r.stderr
