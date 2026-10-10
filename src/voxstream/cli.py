"""Command line: serve, download-models, verify-voices."""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import signal
import sys
import urllib.request
from pathlib import Path

from voxstream.config import Settings

MODEL_RELEASE_URL = "https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.1"
MODEL_FILES = ("kokoro-v1.0.onnx", "voices-v1.0.bin")


def sha256_of(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def cmd_download_models(settings: Settings, files: tuple[str, ...] = MODEL_FILES) -> int:
    models = Path(settings.models_dir)
    models.mkdir(parents=True, exist_ok=True)
    for name in files:
        dest = models / name
        if dest.exists():
            print(f"{name}: already present")
            continue
        url = f"{MODEL_RELEASE_URL}/{name}"
        print(f"{name}: downloading from {url}")
        tmp = dest.with_suffix(dest.suffix + ".part")
        try:
            urllib.request.urlretrieve(url, tmp)
        except OSError as exc:
            tmp.unlink(missing_ok=True)
            print(f"Download failed ({type(exc).__name__}). Check your network and retry.")
            return 1
        tmp.rename(dest)
    lines = [f"{sha256_of(models / n)}  {n}" for n in files if (models / n).exists()]
    (models / "CHECKSUMS.txt").write_text("\n".join(lines) + "\n")
    print("\n".join(lines))
    return 0


async def _serve(settings: Settings) -> None:
    from voxstream.engines.registry import create_engine
    from voxstream.logging import setup_logging
    from voxstream.transports.websocket.server import VoxStreamServer

    setup_logging()
    engine = create_engine(settings.engine, settings)
    server = VoxStreamServer(settings, engine)
    await server.start()
    print(f"voxstream listening on ws://{settings.host}:{server.port}/v1/stream", flush=True)
    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, stop.set)
    await stop.wait()
    await server.close()  # also calls engine.stop()


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="voxstream")
    sub = p.add_subparsers(dest="command", required=True)
    sub.add_parser("serve", help="run the WebSocket streaming service")
    sub.add_parser("download-models", help="download Kokoro model files into models/")
    v = sub.add_parser("verify-voices", help="check which Kokoro voices speak intelligible Spanish")
    v.add_argument("--voices", nargs="+", help="voices to verify (default: all candidates)")
    v.add_argument("--signoff", metavar="VOICE", help="record manual listening sign-off")
    v.add_argument("--by", default=None, help="name recorded with --signoff")
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    settings = Settings()
    if args.command == "download-models":
        return cmd_download_models(settings)
    if args.command == "serve":
        try:
            settings.validate_bind()
        except ValueError as exc:
            print(exc, file=sys.stderr)
            return 2
        asyncio.run(_serve(settings))
        return 0
    if args.command == "verify-voices":
        from voxstream.verification.spanish import run_cli

        return run_cli(settings, args.voices, args.signoff, args.by)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
