"""Read what the service reports on /readyz: active engine, readiness and voices."""

from __future__ import annotations

import asyncio
import json
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from urllib.parse import urlsplit

REASON_LIMIT = 200
KNOWN_ENGINES = ("kokoro", "vibevoice")
_DISPLAY = {"kokoro": "Kokoro", "vibevoice": "VibeVoice"}
SERVICE_DEFAULT_VOICE = "Service default"


@dataclass(frozen=True)
class ServiceInfo:
    reachable: bool
    engine: str | None = None
    ready: bool = False
    reason: str | None = None
    voices: list[str] = field(default_factory=list)

    @property
    def display_name(self) -> str:
        return display_name(self.engine)


UNKNOWN = ServiceInfo(reachable=False)


def display_name(engine: str | None) -> str:
    if engine is None:
        return "Unknown"
    return _DISPLAY.get(engine, engine)


def other_engines(engine: str | None) -> list[str]:
    return [e for e in KNOWN_ENGINES if e != engine]


def restart_hint(other: str, active: str | None) -> str:
    active_name = display_name(active) if active else "another engine"
    return (
        f"{display_name(other)} is not running. The service runs {active_name}; "
        f"restart it with VOXSTREAM_ENGINE={other} and press Refresh."
    )


def voice_choices(info: ServiceInfo) -> tuple[list[str], str | None]:
    """Voices to offer and the preselected one; empty list means fallback (service default)."""
    if not info.voices:
        return [], None
    return list(info.voices), info.voices[0]


def info_line(info: ServiceInfo) -> str:
    if not info.reachable or info.engine is None:
        return "Engine unknown: service info unavailable; using the service default voice"
    if info.ready:
        return f"{info.display_name} · ready"
    return f"{info.display_name} · not ready: {info.reason or 'no reason given'}"


def readyz_url(service_url: str) -> str:
    parts = urlsplit(service_url)
    scheme = "https" if parts.scheme == "wss" else "http"
    return f"{scheme}://{parts.netloc}/readyz"


def _parse(body: bytes) -> ServiceInfo:
    data = json.loads(body)
    if not isinstance(data, dict):
        return UNKNOWN
    engine = data.get("engine")
    reason = data.get("reason")
    voices = data.get("voices")
    return ServiceInfo(
        reachable=True,
        engine=engine if isinstance(engine, str) else None,
        ready=data.get("ready") is True,
        reason=str(reason)[:REASON_LIMIT] if reason else None,
        voices=[v for v in voices if isinstance(v, str)] if isinstance(voices, list) else [],
    )


def _fetch(url: str, timeout_s: float) -> ServiceInfo:
    try:
        try:
            with urllib.request.urlopen(url, timeout=timeout_s) as resp:  # noqa: S310
                return _parse(resp.read())
        except urllib.error.HTTPError as exc:
            if exc.code == 503:
                return _parse(exc.read())
            return UNKNOWN
    except (OSError, ValueError):  # URLError, timeouts, bad JSON (JSONDecodeError)
        return UNKNOWN


async def fetch_service_info(service_url: str, timeout_s: float = 2.0) -> ServiceInfo:
    return await asyncio.to_thread(_fetch, readyz_url(service_url), timeout_s)
