"""Minimal HTTP listener for ``/healthz`` and ``/readyz`` when WebSocket is disabled."""

from __future__ import annotations

import asyncio
import json

from voxstream.core.service import VoxStreamService

READ_TIMEOUT_S = 5.0
MAX_REQUEST_LINE = 2048
MAX_HEADER_BYTES = 8192

_REASONS = {200: "OK", 404: "Not Found", 405: "Method Not Allowed", 503: "Service Unavailable"}


class HealthServer:
    def __init__(self, service: VoxStreamService, host: str, port: int) -> None:
        self.service = service
        self.host = host
        self._port = port
        self._server: asyncio.Server | None = None

    @property
    def port(self) -> int:
        assert self._server is not None
        return int(self._server.sockets[0].getsockname()[1])

    async def start(self) -> None:
        self._server = await asyncio.start_server(self._handle, self.host, self._port)

    async def close(self) -> None:
        if self._server is not None:
            self._server.close()
            await self._server.wait_closed()

    async def _handle(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        try:
            status, body, ctype = await asyncio.wait_for(self._respond(reader), READ_TIMEOUT_S)
        except (TimeoutError, ValueError, ConnectionError, asyncio.LimitOverrunError):
            status, body, ctype = 404, "not found\n", "text/plain"
        try:
            data = body.encode()
            head = (
                f"HTTP/1.1 {status} {_REASONS[status]}\r\nContent-Type: {ctype}\r\n"
                f"Content-Length: {len(data)}\r\nConnection: close\r\n\r\n"
            )
            writer.write(head.encode() + data)
            await asyncio.wait_for(writer.drain(), READ_TIMEOUT_S)
        except (TimeoutError, ConnectionError):
            pass
        finally:
            writer.close()

    async def _respond(self, reader: asyncio.StreamReader) -> tuple[int, str, str]:
        line = await reader.readline()
        if len(line) > MAX_REQUEST_LINE:
            raise ValueError("request line too long")
        parts = line.decode("latin-1").split()
        read = 0
        while read < MAX_HEADER_BYTES:  # drain headers, bounded
            header = await reader.readline()
            read += len(header)
            if header in (b"\r\n", b"\n", b""):
                break
        if len(parts) < 2 or parts[0] != "GET":
            return 405, "method not allowed\n", "text/plain"
        path = parts[1].split("?", 1)[0]
        if path == "/healthz":
            return 200, "ok\n", "text/plain"
        if path == "/readyz":
            body = self.service.readiness()
            return (200 if body["ready"] else 503), json.dumps(body) + "\n", "application/json"
        return 404, "not found\n", "text/plain"
