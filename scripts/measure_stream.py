"""Measure streaming latency against a running service (Spanish text only).

    uv run python scripts/measure_stream.py --trials 20 [--transport websocket|grpc]
        [--url ws://127.0.0.1:8765/v1/stream | --grpc-target 127.0.0.1:50051]

Reports median and p95 for time to first audio (from the end of the text piece that completes the
first sentence), real-time factor, inter-frame delay, plus peak RSS of the server process when
--pid is given. Generation time (from the `completed` timing) and delivery time are separate.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import statistics
import subprocess
import time

import websockets
from grpc import aio

from voxstream.transports.grpc.gen import voxstream_pb2 as pb
from voxstream.transports.grpc.gen import voxstream_pb2_grpc as pb_grpc

TEXT = (
    "Hola, ¿cómo estás hoy? Me alegra mucho verte por aquí. Hoy hace un día muy bonito en la "
    "ciudad, y mañana iremos a la montaña con los niños. Después tomaremos un café caliente."
)
FIRST_SENTENCE = "Hola, ¿cómo estás hoy?"


def pct(values: list[float], q: float) -> float:
    values = sorted(values)
    return values[min(len(values) - 1, round(q * (len(values) - 1)))]


async def trial(url: str) -> dict[str, float]:
    async with websockets.connect(url) as ws:
        await ws.send(json.dumps({"type": "start"}))
        rid = json.loads(await ws.recv())["request_id"]
        cut = len(FIRST_SENTENCE)
        t_first_sentence = 0.0
        for piece in (TEXT[:cut], TEXT[cut:]):
            await ws.send(json.dumps({"type": "text", "request_id": rid, "text": piece}))
            if not t_first_sentence:
                t_first_sentence = time.monotonic()
        await ws.send(json.dumps({"type": "end", "request_id": rid}))
        stamps: list[float] = []
        done: dict[str, object] = {}
        async for m in ws:
            if isinstance(m, bytes):
                stamps.append(time.monotonic())
            else:
                msg = json.loads(m)
                if msg["type"] == "completed":
                    done = msg
                    break
                if msg["type"] == "error":
                    raise RuntimeError(msg["code"])
    gaps = [(b - a) * 1000 for a, b in zip(stamps, stamps[1:], strict=False)]
    timing = done["timing"]
    assert isinstance(timing, dict)
    return {
        "ttfa_ms": (stamps[0] - t_first_sentence) * 1000,
        "rtf": float(timing["rtf"]),
        "generation_ms": float(timing["generation_ms"]),
        "delivery_ms": float(timing["delivery_ms"]),
        "max_gap_ms": max(gaps) if gaps else 0.0,
        "median_gap_ms": statistics.median(gaps) if gaps else 0.0,
    }


async def trial_grpc(target: str) -> dict[str, float]:
    async with aio.insecure_channel(target) as channel:
        outbound: asyncio.Queue[pb.ClientEvent | None] = asyncio.Queue()

        async def requests():  # type: ignore[no-untyped-def]
            while (ev := await outbound.get()) is not None:
                yield ev

        call = pb_grpc.SynthesizerStub(channel).Stream(requests())
        outbound.put_nowait(pb.ClientEvent(start=pb.Start()))
        cut = len(FIRST_SENTENCE)
        t_first_sentence = 0.0
        stamps: list[float] = []
        done: dict[str, float] = {}
        async for ev in call:
            case = ev.WhichOneof("event")
            if case == "started":
                for piece in (TEXT[:cut], TEXT[cut:]):
                    outbound.put_nowait(pb.ClientEvent(text=pb.Text(text=piece)))
                    if not t_first_sentence:
                        t_first_sentence = time.monotonic()
                outbound.put_nowait(pb.ClientEvent(end=pb.End()))
            elif case == "audio":
                stamps.append(time.monotonic())
            elif case == "completed":
                done = dict(ev.completed.timing)
            elif case == "error":
                raise RuntimeError(ev.error.code)
        outbound.put_nowait(None)
    gaps = [(b - a) * 1000 for a, b in zip(stamps, stamps[1:], strict=False)]
    return {
        "ttfa_ms": (stamps[0] - t_first_sentence) * 1000,
        "rtf": done["rtf"],
        "generation_ms": done["generation_ms"],
        "delivery_ms": done["delivery_ms"],
        "max_gap_ms": max(gaps) if gaps else 0.0,
        "median_gap_ms": statistics.median(gaps) if gaps else 0.0,
    }


def rss_mb(pid: int) -> float:
    out = subprocess.run(["ps", "-o", "rss=", "-p", str(pid)], capture_output=True, text=True)
    return int(out.stdout.strip() or 0) / 1024


async def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--transport", choices=["websocket", "grpc"], default="websocket")
    p.add_argument("--url", default="ws://127.0.0.1:8765/v1/stream")
    p.add_argument("--grpc-target", default="127.0.0.1:50051")
    p.add_argument("--trials", type=int, default=20)
    p.add_argument("--pid", type=int, help="server pid, for memory")
    args = p.parse_args()
    results, peak = [], 0.0
    for i in range(args.trials):
        if args.transport == "grpc":
            results.append(await trial_grpc(args.grpc_target))
        else:
            results.append(await trial(args.url))
        if args.pid:
            peak = max(peak, rss_mb(args.pid))
        print(f"trial {i + 1}: ttfa={results[-1]['ttfa_ms']:.0f} ms rtf={results[-1]['rtf']:.2f}")
    print(f"\ntransport: {args.transport} (local loopback, not a remote network)")
    print("metric            median      p95")
    for key in results[0]:
        vals = [r[key] for r in results]
        print(f"{key:<16} {statistics.median(vals):>8.2f} {pct(vals, 0.95):>8.2f}")
    print("first (cold) trial ttfa_ms:", round(results[0]["ttfa_ms"]))
    if args.pid:
        print(f"peak server RSS: {peak:.0f} MB (ceiling 4096 MB)")


if __name__ == "__main__":
    asyncio.run(main())
