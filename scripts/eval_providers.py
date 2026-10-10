"""Compare model variants / execution providers: latency, peak memory, and Spanish WER.

    uv run python scripts/eval_providers.py --model-file kokoro-v1.0.int8.onnx --provider cpu

Run once per configuration (each run is a fresh process so peak RSS is comparable).
"""

from __future__ import annotations

import argparse
import resource
import time

from voxstream.config import Settings
from voxstream.verification import spanish as sp


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--model-file", default="kokoro-v1.0.onnx")
    p.add_argument("--provider", default="cpu")
    p.add_argument("--voice", default="ef_dora")
    p.add_argument("--sentences", type=int, default=6)
    args = p.parse_args()

    settings = Settings(
        _env_file=None,
        model_file=args.model_file,
        execution_provider=args.provider,
        allow_unverified_voices=True,
    )
    t0 = time.perf_counter()
    synth = sp._kokoro_synth(settings)
    load_s = time.perf_counter() - t0
    sentences = sp.load_sentences()[: args.sentences]
    synth(sentences[0], args.voice)  # warm-up
    gen = audio = 0.0
    clips = []
    for s in sentences:
        t = time.perf_counter()
        pcm = synth(s, args.voice)
        gen += time.perf_counter() - t
        audio += len(pcm) / 24000
        clips.append(pcm)
    peak_mb = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1e6
    transcribe, _ = sp._whisper_transcribe()
    wers = [sp.default_wer(s, transcribe(c)) for s, c in zip(sentences, clips, strict=True)]
    print(
        f"{args.model_file} / {args.provider}: load={load_s:.1f}s rtf={gen / audio:.2f} "
        f"mean_wer={sum(wers) / len(wers):.3f} max_wer={max(wers):.3f} peak_rss={peak_mb:.0f}MB"
    )


if __name__ == "__main__":
    main()
