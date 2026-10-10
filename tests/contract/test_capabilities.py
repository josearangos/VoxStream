from helpers import client_for


async def test_capabilities(serve):
    async with serve() as server, client_for(server) as c:
        await c.send(type="capabilities")
        caps = await c.recv_json()
        assert caps["type"] == "capabilities"
        assert caps["languages"] == ["es"]
        assert caps["voices"]
        assert caps["audio_format"] == {
            "encoding": "pcm_s16le",
            "sample_rate": 24000,
            "channels": 1,
        }
        assert caps["streaming_mode"] in ("incremental", "segmented", "complete_then_chunked")
        assert "supports_cancel" in caps and "execution_provider" in caps


async def test_kokoro_reports_segmented():
    from voxstream.config import Settings
    from voxstream.engines.kokoro.engine import KokoroEngine

    assert KokoroEngine(Settings(_env_file=None)).capabilities().streaming_mode == "segmented"


async def test_capabilities_while_request_active(serve):
    """WebSocket rejects the query with BUSY; gRPC capabilities is a separate unary call."""
    async with serve() as server, client_for(server) as c:
        await c.start()
        await c.send(type="capabilities")
        reply = await c.recv_json()
        if server.transport == "websocket":
            assert reply["type"] == "error" and reply["code"] == "BUSY"
        else:
            assert reply["type"] == "capabilities" and reply["voices"]
        await c.cancel()
        await c.collect()


async def test_http_health_endpoints(serve):
    import urllib.request

    async with serve() as server:
        import asyncio

        def get(path):
            try:
                with urllib.request.urlopen(f"http://127.0.0.1:{server.port}{path}") as r:
                    return r.status, r.read().decode()
            except urllib.error.HTTPError as e:
                return e.code, e.read().decode()

        status, _ = await asyncio.to_thread(get, "/healthz")
        assert status == 200
        status, body = await asyncio.to_thread(get, "/readyz")
        assert status in (200, 503) and "execution_provider" in body
