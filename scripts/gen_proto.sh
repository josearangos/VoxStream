#!/usr/bin/env bash
# Regenerate the gRPC stubs from proto/voxstream/v1/voxstream.proto.
# Usage: scripts/gen_proto.sh [output_dir]   (default: src/voxstream/transports/grpc/gen)
# Output is flat (never gen/voxstream/v1/, which would shadow the real `voxstream` package).
set -euo pipefail
cd "$(dirname "$0")/.."
OUT="${1:-src/voxstream/transports/grpc/gen}"
mkdir -p "$OUT"
uv run python -m grpc_tools.protoc -Iproto/voxstream/v1 \
  --python_out="$OUT" --grpc_python_out="$OUT" --pyi_out="$OUT" voxstream.proto
sed -i.bak 's/^import voxstream_pb2 as /from . import voxstream_pb2 as /' "$OUT/voxstream_pb2_grpc.py"
rm -f "$OUT/voxstream_pb2_grpc.py.bak"
touch "$OUT/__init__.py"
