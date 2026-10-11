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
VIBEVOICE_REPO = "microsoft/VibeVoice-Realtime-0.5B"
VIBEVOICE_VOICES_URL = (
    "https://github.com/user-attachments/files/24035884/experimental_voices_sp.tar.gz"
)
# Pinned on 2026-10-10 from the upstream files (trust on first use); a mismatch means upstream
# changed the files or the download was altered.
VIBEVOICE_VOICE_SHA256 = {
    "sp-Spk2_woman": "f88d2ba4057cc621bbbd0c7bd1a16ac77129008b52488ae15957a238878a8667",
    "sp-Spk3_man": "3275ca5b5dcd11c3ccd1c613e4e70004ee5c92ee293dc6476abae07fd79a72fd",
    "sp-Spk4_woman": "b4e31f86aaabab417f66bdb395bcf282c99546ed98c526cbc9ebd7e696281b93",
    "sp-Spk5_man": "1b805045b5c54ff56dc032a304f92060e0447f3008b0ef73484e9c6a1c49c5b3",
}
VIBEVOICE_MODEL_SHA256 = "7758b150b8139deb48ac1ff6f181f745c8fedd5511232fd974b3eb217d83b514"


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


def cmd_download_vibevoice(settings: Settings) -> int:
    """Fetch the model (Hugging Face) and the Spanish voice presets (upstream GitHub)."""
    import tarfile

    root = Path(settings.vibevoice_model_dir)
    model_dir, voices_dir = root / "model", root / "voices"
    voices_dir.mkdir(parents=True, exist_ok=True)
    if not (model_dir / "model.safetensors").exists():
        print(f"model: downloading from https://huggingface.co/{VIBEVOICE_REPO}")
        try:
            from huggingface_hub import snapshot_download

            snapshot_download(
                VIBEVOICE_REPO,
                local_dir=str(model_dir),
                allow_patterns=["*.json", "*.safetensors"],
            )
        except ImportError:
            print("Needs the 'vibevoice' extra: uv sync --extra vibevoice")
            return 1
        except Exception as exc:
            print(f"Download failed ({type(exc).__name__}). Check your network and retry.")
            return 1
    else:
        print("model: already present")
    if not any(voices_dir.glob("*.pt")):
        print(f"voices: downloading from {VIBEVOICE_VOICES_URL}")
        archive = root / "experimental_voices_sp.tar.gz"
        try:
            urllib.request.urlretrieve(VIBEVOICE_VOICES_URL, archive)
            with tarfile.open(archive) as tar:
                for member in tar.getmembers():
                    name = Path(member.name).name
                    if member.isfile() and name.endswith(".pt"):
                        data = tar.extractfile(member)
                        assert data is not None
                        (voices_dir / name).write_bytes(data.read())
        except (OSError, tarfile.TarError) as exc:
            print(f"Download failed ({type(exc).__name__}). Check your network and retry.")
            return 1
        finally:
            archive.unlink(missing_ok=True)
    else:
        print("voices: already present")
    bad = [
        name
        for name, digest in VIBEVOICE_VOICE_SHA256.items()
        if not (voices_dir / f"{name}.pt").exists()
        or sha256_of(voices_dir / f"{name}.pt") != digest
    ]
    if bad:
        print(f"Checksum mismatch or missing voice presets: {', '.join(bad)}. Not trusting them.")
        for name in bad:
            (voices_dir / f"{name}.pt").unlink(missing_ok=True)
        return 1
    print("Voice presets are pickles from the upstream project; they load with weights_only.")
    model_sha = sha256_of(model_dir / "model.safetensors")
    print("sha256:", model_sha)
    if model_sha != VIBEVOICE_MODEL_SHA256:
        print(
            "Warning: the model file differs from the one verified for this project; "
            "rerun 'voxstream verify-voices --engine vibevoice'."
        )
    return 0


async def _serve(settings: Settings) -> int:
    from voxstream.app import VoxStreamApp
    from voxstream.engines.registry import create_engine
    from voxstream.logging import setup_logging

    setup_logging()
    engine = create_engine(settings.engine, settings)
    app = VoxStreamApp(settings, engine)
    try:
        await app.start()
    except OSError as exc:
        print(f"Could not start: {exc}", file=sys.stderr)
        await engine.stop()
        return 2
    host = settings.host
    if settings.enable_websocket:
        print(f"voxstream WebSocket ws://{host}:{app.port}/v1/stream", flush=True)
    else:
        print(f"voxstream health http://{host}:{app.port}/readyz", flush=True)
    if settings.enable_grpc:
        print(f"voxstream gRPC {host}:{app.grpc_port}", flush=True)
    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, stop.set)
    await stop.wait()
    await app.close()  # also calls engine.stop()
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="voxstream")
    sub = p.add_subparsers(dest="command", required=True)
    sub.add_parser("serve", help="run the streaming service (WebSocket and/or gRPC)")
    d = sub.add_parser("download-models", help="download model files into models/")
    d.add_argument("--engine", choices=["kokoro", "vibevoice"], default="kokoro")
    v = sub.add_parser("verify-voices", help="check which Kokoro voices speak intelligible Spanish")
    v.add_argument("--engine", default=None, help="engine to verify (default: VOXSTREAM_ENGINE)")
    v.add_argument("--voices", nargs="+", help="voices to verify (default: all candidates)")
    v.add_argument("--signoff", metavar="VOICE", help="record manual listening sign-off")
    v.add_argument("--by", default=None, help="name recorded with --signoff")
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    settings = Settings()
    if args.command == "download-models":
        if args.engine == "vibevoice":
            return cmd_download_vibevoice(settings)
        return cmd_download_models(settings)
    if args.command == "serve":
        try:
            settings.validate_transports()
            settings.validate_bind()
        except ValueError as exc:
            print(exc, file=sys.stderr)
            return 2
        return asyncio.run(_serve(settings))
    if args.command == "verify-voices":
        from voxstream.verification.spanish import run_cli

        return run_cli(settings, args.voices, args.signoff, args.by, args.engine)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
