"""Transmite texto en español a VoxStream por gRPC y guarda el audio en un archivo WAV.

uv run python examples/grpc_client.py --simulate-llm "Hola, ¿cómo estás hoy? Me alegra verte."
"""

from __future__ import annotations

import argparse
import asyncio
import json
import time
import wave
from collections.abc import AsyncIterator

import grpc
from grpc import aio

from voxstream.transports.grpc.gen import voxstream_pb2 as pb
from voxstream.transports.grpc.gen import voxstream_pb2_grpc as pb_grpc

DEFAULT_TEXT = "Hola, ¿cómo estás hoy? Me alegra mucho verte. Hoy hace un día muy bonito."
SAMPLE_RATE = 24000


async def run(args: argparse.Namespace) -> int:
    pieces = (
        [args.text[i : i + args.piece_size] for i in range(0, len(args.text), args.piece_size)]
        if args.simulate_llm
        else [args.text]
    )
    outbound: asyncio.Queue[pb.ClientEvent | None] = asyncio.Queue()

    async def requests() -> AsyncIterator[pb.ClientEvent]:
        while (event := await outbound.get()) is not None:
            yield event

    async def send_text() -> None:
        for piece in pieces:
            outbound.put_nowait(pb.ClientEvent(text=pb.Text(text=piece)))
            if args.simulate_llm:
                await asyncio.sleep(args.pause)
        outbound.put_nowait(pb.ClientEvent(end=pb.End()))

    start = pb.Start(voice=args.voice) if args.voice else pb.Start()
    outbound.put_nowait(pb.ClientEvent(start=start))
    pcm = bytearray()
    chunks = 0
    first_audio: float | None = None
    sample_rate = SAMPLE_RATE
    sender: asyncio.Task[None] | None = None
    async with aio.insecure_channel(f"{args.host}:{args.port}") as channel:
        call = pb_grpc.SynthesizerStub(channel).Stream(requests())  # type: ignore[no-untyped-call]
        t0 = time.monotonic()
        try:
            async for event in call:
                case = event.WhichOneof("event")
                if case == "started":
                    sample_rate = event.started.stream.sample_rate
                    print("Started:", event.started.stream.voice, event.started.request_id)
                    sender = asyncio.create_task(send_text())
                elif case == "audio":
                    pcm += event.audio.pcm
                    chunks += 1
                    if first_audio is None:
                        first_audio = time.monotonic() - t0
                        print(f"Time to first audio: {first_audio * 1000:.0f} ms")
                    if args.cancel_after_chunks and chunks >= args.cancel_after_chunks:
                        outbound.put_nowait(pb.ClientEvent(cancel=pb.Cancel()))
                        args.cancel_after_chunks = 0
                elif case == "completed":
                    done = event.completed
                    print(
                        "Completed:",
                        json.dumps(
                            {
                                "audio_frames": done.audio_frames,
                                "audio_ms": done.audio_ms,
                                "chars": done.chars,
                                "timing": dict(done.timing),
                            }
                        ),
                    )
                elif case == "cancelled":
                    print("Cancelled: audio_frames_sent =", event.cancelled.audio_frames_sent)
                elif case == "error":
                    e = event.error
                    print(f"Error: {e.code} ({e.category}, retryable={e.retryable}): {e.message}")
                    if not e.HasField("request_id"):
                        return 1
        except aio.AioRpcError as exc:
            if exc.code() == grpc.StatusCode.UNAVAILABLE:
                print(
                    f"No se pudo conectar con {args.host}:{args.port}. ¿Está corriendo el servicio?"
                )
            else:
                print(f"gRPC error: {exc.code().name}")
            return 1
        finally:
            if sender is not None:
                sender.cancel()
            outbound.put_nowait(None)
    if not pcm:
        return 0
    with wave.open(args.output, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sample_rate)
        w.writeframes(bytes(pcm))
    print(f"Wrote {args.output} ({len(pcm) / 2 / sample_rate:.2f} s of audio)")
    return 0


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("text", nargs="?", default=DEFAULT_TEXT, help="texto en español")
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--port", type=int, default=50051)
    p.add_argument("--voice", help="voz verificada, por ejemplo em_alex")
    p.add_argument("--output", default="out.wav", help="archivo WAV de salida")
    p.add_argument(
        "--simulate-llm", action="store_true", help="envía trozos pequeños de texto con pausas"
    )
    p.add_argument("--piece-size", type=int, default=6, help="caracteres por trozo")
    p.add_argument("--pause", type=float, default=0.05, help="segundos entre trozos")
    p.add_argument("--cancel-after-chunks", type=int, default=0, help="cancela tras N bloques")
    return asyncio.run(run(p.parse_args()))


if __name__ == "__main__":
    raise SystemExit(main())
