"""Deterministic mock engine for tests: audio length is a function of text length."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator

import numpy as np

from voxstream.engines.base import (
    AudioBlock,
    CancelToken,
    EngineCapabilities,
    EngineError,
)

SAMPLE_RATE = 24000


class MockEngine:
    name = "mock"

    def __init__(
        self,
        *,
        delay_s: float = 0.0,
        ms_per_char: int = 40,
        fail_at_segment: int | None = None,
        fail_with: BaseException | None = None,
        block_ms: int = 200,
        voices: list[str] | None = None,
    ) -> None:
        self.delay_s = delay_s
        self.ms_per_char = ms_per_char
        self.fail_at_segment = fail_at_segment
        self.fail_with = fail_with
        self.block_ms = block_ms
        self.voices = ["mock_es"] if voices is None else voices
        self.calls = 0
        self.started = False
        self.stopped = False
        self.synthesized: list[str] = []

    async def start(self) -> None:
        self.started = True

    def capabilities(self) -> EngineCapabilities:
        return EngineCapabilities(
            name=self.name,
            version="1",
            languages=["es"],
            voices=list(self.voices),
            streaming_mode="segmented",
            supports_cancel="per-block",
            execution_provider="none",
            memory_notes="negligible",
        )

    async def synthesize(
        self, text: str, voice: str, cancel: CancelToken
    ) -> AsyncIterator[AudioBlock]:
        index = self.calls
        self.calls += 1
        if self.delay_s:
            await asyncio.sleep(self.delay_s)
        if cancel.cancelled:
            return
        if self.fail_at_segment == index:
            raise self.fail_with or EngineError("injected failure")
        self.synthesized.append(text)
        total = SAMPLE_RATE * self.ms_per_char * len(text) // 1000
        per_block = SAMPLE_RATE * self.block_ms // 1000
        t = np.arange(total)
        wave = (np.sin(2 * np.pi * 220 * t / SAMPLE_RATE) * 3000).astype(np.int16)
        for off in range(0, total, per_block):
            if cancel.cancelled:
                return
            yield AudioBlock(wave[off : off + per_block], SAMPLE_RATE, 1)
            await asyncio.sleep(0)

    async def stop(self) -> None:
        self.stopped = True
