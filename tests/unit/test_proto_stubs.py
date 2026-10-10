import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
GEN = ROOT / "src/voxstream/transports/grpc/gen"


def test_stubs_import():
    from voxstream.transports.grpc.gen import voxstream_pb2, voxstream_pb2_grpc

    assert voxstream_pb2.DESCRIPTOR.package == "voxstream.v1"
    assert hasattr(voxstream_pb2_grpc, "SynthesizerStub")


def test_committed_stubs_match_proto(tmp_path):
    """Regenerate into a temp dir with the script's command and diff against the committed files."""
    out = tmp_path / "gen"
    subprocess.run(
        [str(ROOT / "scripts/gen_proto.sh"), str(out)],
        check=True,
        capture_output=True,
    )
    for name in ("voxstream_pb2.py", "voxstream_pb2.pyi", "voxstream_pb2_grpc.py"):
        assert (out / name).read_text() == (GEN / name).read_text(), (
            f"{name} is stale: run scripts/gen_proto.sh"
        )


def test_proto_copy_matches_contract():
    contract = ROOT / "specs/002-grpc-streaming-transport/contracts/voxstream.proto"
    if contract.exists():
        assert (ROOT / "proto/voxstream/v1/voxstream.proto").read_text() == contract.read_text()
