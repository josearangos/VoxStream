import asyncio

from helpers import client_for

LONG = "Esta es una oración larga de prueba para el audio. " * 6


async def test_cancel_after_first_frame(serve):
    async with serve(mock={"delay_s": 0.02}) as server, client_for(server) as c:
        await c.start()
        await c.text(LONG)
        while not isinstance(await c.recv(120), bytes):
            pass
        await c.cancel()
        frames, controls = await c.collect(timeout=30)
        cancelled = [m for m in controls if m["type"] == "cancelled"]
        assert len(cancelled) == 1 and cancelled[0]["request_id"] == c.request_id
        assert not [m for m in controls if m["type"] in ("completed", "error")]
        # nothing follows the terminal message
        await c.text("más texto")
        await c.end()
        await asyncio.sleep(0.2)
        extra = []
        try:
            while True:
                extra.append(await c.recv(0.3))
        except TimeoutError:
            pass
        assert extra == [], "text/end after cancel must be ignored"


async def test_new_start_after_cancel(serve):
    async with serve() as server, client_for(server) as c:
        await c.start()
        await c.cancel()
        await c.collect()
        second = await c.start()
        assert second["type"] == "started"
        assert second["request_id"] != ""


async def test_cancel_racing_completion_yields_exactly_one_terminal(serve):
    async with serve() as server, client_for(server) as c:
        await c.start()
        await c.text("Hola.")
        await c.end()
        await c.cancel()
        _, controls = await c.collect(timeout=60)
        terminals = [m for m in controls if m["type"] in ("completed", "cancelled")]
        assert len(terminals) == 1
        await asyncio.sleep(0.2)
        # no second terminal arrives
        try:
            extra = await c.recv(0.3)
        except TimeoutError:
            extra = None
        assert extra is None or '"error"' in extra  # at most a NO_ACTIVE_REQUEST on the late cancel
