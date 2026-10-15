import json

from demo.service_info import UNKNOWN, ServiceInfo

from demo import service_info as si
from helpers import running_server
from voxstream.engines.mock import MockEngine


def test_readyz_url_ws_and_wss() -> None:
    assert si.readyz_url("ws://h:8765/v1/stream") == "http://h:8765/readyz"
    assert si.readyz_url("wss://h:1/v1/stream") == "https://h:1/readyz"


def test_parse_ready_body() -> None:
    body = json.dumps({"ready": True, "engine": "vibevoice", "voices": ["a", "b"]}).encode()
    info = si._parse(body)
    assert info == ServiceInfo(True, "vibevoice", True, None, ["a", "b"])


def test_parse_not_ready_truncates_reason() -> None:
    body = json.dumps({"ready": False, "engine": "kokoro", "reason": "x" * 500}).encode()
    info = si._parse(body)
    assert not info.ready and info.reason is not None and len(info.reason) == 200


def test_display_names_and_hints() -> None:
    assert ServiceInfo(True, "kokoro").display_name == "Kokoro"
    assert ServiceInfo(True, "vibevoice").display_name == "VibeVoice"
    assert UNKNOWN.display_name == "Unknown"
    assert si.other_engines("vibevoice") == ["kokoro"]
    hint = si.restart_hint("kokoro", "vibevoice")
    assert "VOXSTREAM_ENGINE=kokoro" in hint and "VibeVoice" in hint


def test_voice_choices() -> None:
    assert si.voice_choices(ServiceInfo(True, "kokoro", True, None, ["a", "b"])) == (
        ["a", "b"],
        "a",
    )
    assert si.voice_choices(UNKNOWN) == ([], None)


async def test_unreachable_is_unknown() -> None:
    assert await si.fetch_service_info("ws://127.0.0.1:1/v1/stream") == UNKNOWN


async def test_live_server_info() -> None:
    async with running_server(MockEngine(voices=["v1", "v2"])) as server:
        info = await si.fetch_service_info(f"ws://127.0.0.1:{server.port}/v1/stream")
        assert info.reachable and info.ready and info.voices == ["v1", "v2"]
        # unknown path -> 404 -> UNKNOWN
        bad = si._fetch(f"http://127.0.0.1:{server.port}/nope", 2.0)
        assert bad == UNKNOWN


def test_non_json_is_unknown(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    class R:
        def __enter__(self):
            return self  # noqa: E704

        def __exit__(self, *a):
            return False  # noqa: E704

        def read(self):
            return b"<html>"  # noqa: E704

    monkeypatch.setattr(si.urllib.request, "urlopen", lambda *a, **k: R())
    assert si._fetch("http://x/readyz", 1.0) == UNKNOWN
