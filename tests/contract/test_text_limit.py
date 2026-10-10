from helpers import client_for


async def test_boundary_2000(serve):
    text = ("Hola amigo. " * 200)[:2000]
    async with serve() as server, client_for(server) as c:
        await c.start()
        await c.text(text)
        await c.end()
        _, controls = await c.collect(timeout=300)
        assert controls[-1]["type"] == "completed", controls[-1]
        assert controls[-1]["chars"] == 2000


async def test_crossing_limit_fails_but_prior_audio_valid(serve):
    async with serve(max_text_chars=100) as server, client_for(server) as c:
        await c.start()
        await c.text("Hola mundo. Esto es una prueba. ")  # 32 chars, 2 complete sentences
        await c.text("x" * 80)  # crosses the limit
        frames, controls = await c.collect(timeout=60)
        err = controls[-1]
        assert err["type"] == "error" and err["code"] == "TEXT_TOO_LONG"
        assert err["category"] == "validation" and err["retryable"] is False
        assert err["request_id"] == c.request_id
        assert [f.sequence for f in frames] == list(range(len(frames)))
        if server.transport == "websocket":  # a gRPC call is over after its terminal event
            await c.text("más")
            again = await c.recv_json()
            assert again["code"] == "NO_ACTIVE_REQUEST"
        assert server.admission.active == 0
