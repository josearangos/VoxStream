"""Stream Spanish text to VoxStream and save the audio as a WAV file.

uv run python examples/ws_client.py "Hola, ¿cómo estás hoy? Me alegra verte." --simulate-llm
"""

from __future__ import annotations

import argparse
import asyncio
import json
import struct
import time
import uuid
import wave

import websockets

DEFAULT_TEXT = "Hola, ¿cómo estás hoy? Me alegra mucho verte. Hoy hace un día muy bonito."


def decode(frame: bytes) -> tuple[uuid.UUID, int, bool, bytes]:
    seq, flags = struct.unpack(">IB", frame[16:21])
    return uuid.UUID(bytes=frame[:16]), seq, bool(flags & 1), frame[21:]


async def run(args: argparse.Namespace) -> int:
    pieces = (
        [args.text[i : i + args.piece_size] for i in range(0, len(args.text), args.piece_size)]
        if args.simulate_llm
        else [args.text]
    )
    async with websockets.connect(args.url) as ws:
        start: dict[str, str] = {"type": "start"}
        if args.voice:
            start["voice"] = args.voice
        await ws.send(json.dumps(start))
        started = json.loads(await ws.recv())
        if started["type"] != "started":
            print("Rejected:", started)
            return 1
        rid, stream = started["request_id"], started["stream"]
        print("Started:", stream)
        t0 = time.monotonic()
        pcm = bytearray()
        chunks = 0
        first_audio: float | None = None

        async def send_text() -> None:
            for piece in pieces:
                await ws.send(json.dumps({"type": "text", "request_id": rid, "text": piece}))
                if args.simulate_llm:
                    await asyncio.sleep(args.pause)
            await ws.send(json.dumps({"type": "end", "request_id": rid}))

        sender = asyncio.create_task(send_text())
        try:
            async for message in ws:
                if isinstance(message, bytes):
                    _, _, _, payload = decode(message)
                    pcm += payload
                    chunks += 1
                    if first_audio is None:
                        first_audio = time.monotonic() - t0
                        print(f"Time to first audio: {first_audio * 1000:.0f} ms")
                    if args.cancel_after_chunks and chunks >= args.cancel_after_chunks:
                        await ws.send(json.dumps({"type": "cancel", "request_id": rid}))
                        args.cancel_after_chunks = 0
                    continue
                msg = json.loads(message)
                if msg["type"] in ("completed", "cancelled", "error"):
                    print(msg["type"].capitalize() + ":", json.dumps(msg, ensure_ascii=False))
                    break
        finally:
            sender.cancel()
    with wave.open(args.output, "wb") as w:
        w.setnchannels(stream["channels"])
        w.setsampwidth(2)
        w.setframerate(stream["sample_rate"])
        w.writeframes(bytes(pcm))
    print(f"Wrote {args.output} ({len(pcm) / 2 / stream['sample_rate']:.2f} s of audio)")
    return 0


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("text", nargs="?", default=DEFAULT_TEXT)
    p.add_argument("--url", default="ws://127.0.0.1:8765/v1/stream")
    p.add_argument("--voice")
    p.add_argument("--output", default="out.wav")
    p.add_argument("--simulate-llm", action="store_true", help="send small pieces with pauses")
    p.add_argument("--piece-size", type=int, default=6)
    p.add_argument("--pause", type=float, default=0.05)
    p.add_argument("--cancel-after-chunks", type=int, default=0)
    return asyncio.run(run(p.parse_args()))


if __name__ == "__main__":
    raise SystemExit(main())
