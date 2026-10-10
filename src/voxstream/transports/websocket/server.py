"""WebSocket transport: /v1/stream plus plain-HTTP /healthz and /readyz on the same port."""

from __future__ import annotations

import asyncio
import json
from collections.abc import Callable
from dataclasses import dataclass, field
from http import HTTPStatus
from typing import Any

from websockets.asyncio.server import Server, ServerConnection, serve
from websockets.exceptions import ConnectionClosed
from websockets.http11 import Request, Response

from voxstream.core.admission import AdmissionController
from voxstream.core.frames import AudioFrame
from voxstream.core.service import VoxStreamService
from voxstream.core.session import Session, map_exception
from voxstream.engines.base import TTSEngine
from voxstream.errors import ErrorCode, VoxStreamError
from voxstream.logging import logger, transport_var
from voxstream.transports.websocket import messages as msg
from voxstream.transports.websocket.framing import encode_frame

STREAM_PATH = "/v1/stream"
INBOX_SIZE = 8
MAX_MESSAGE_BYTES = 64 * 1024
_FAIL_REQUEST_CODES = (ErrorCode.TEXT_TOO_LONG, ErrorCode.EMPTY_REQUEST)


@dataclass(eq=False)
class _Conn:
    ws: ServerConnection
    inbox: asyncio.Queue[msg.AnyClientMessage] = field(
        default_factory=lambda: asyncio.Queue(INBOX_SIZE)
    )
    session: Session | None = None
    watcher: asyncio.Task[None] | None = None
    release: Callable[[], None] | None = None
    last_cancelled: str | None = None
    closed: bool = False


class VoxStreamServer:
    def __init__(self, service: VoxStreamService) -> None:
        self.service = service
        self.settings = service.settings
        self._server: Server | None = None
        self._conns: set[_Conn] = set()

    @property
    def engine(self) -> TTSEngine:
        return self.service.engine

    @property
    def admission(self) -> AdmissionController:
        return self.service.admission

    # -- lifecycle ----------------------------------------------------------------------------

    async def start(self) -> None:
        self.settings.validate_bind()
        self._server = await serve(
            self._handle,
            self.settings.host,
            self.settings.port,
            process_request=self._process_request,
            max_size=MAX_MESSAGE_BYTES,
            close_timeout=2,
        )

    @property
    def port(self) -> int:
        assert self._server is not None
        return int(next(iter(self._server.sockets)).getsockname()[1])

    async def serve_forever(self) -> None:
        assert self._server is not None
        await self._server.serve_forever()

    async def close(self) -> None:
        if self._server is not None:
            self._server.close()
        for conn in list(self._conns):
            if conn.session is not None:
                conn.session.cancel()
        if self._server is not None:
            await self._server.wait_closed()

    async def __aenter__(self) -> VoxStreamServer:
        await self.start()
        return self

    async def __aexit__(self, *exc: object) -> None:
        await self.close()

    # -- health -------------------------------------------------------------------------------

    def _process_request(self, connection: ServerConnection, request: Request) -> Response | None:
        path = request.path.split("?", 1)[0]
        if path == "/healthz":
            return connection.respond(HTTPStatus.OK, "ok\n")
        if path == "/readyz":
            body = self.service.readiness()
            status = HTTPStatus.OK if body["ready"] else HTTPStatus.SERVICE_UNAVAILABLE
            resp = connection.respond(status, json.dumps(body) + "\n")
            resp.headers["Content-Type"] = "application/json"
            return resp
        if path != STREAM_PATH:
            return connection.respond(HTTPStatus.NOT_FOUND, "not found\n")
        return None

    # -- connection handling ------------------------------------------------------------------

    async def _handle(self, ws: ServerConnection) -> None:
        transport_var.set("websocket")
        conn = _Conn(ws)
        self._conns.add(conn)
        worker = asyncio.create_task(self._worker(conn))
        try:
            await self._reader(conn)
        except ConnectionClosed:
            pass
        finally:
            conn.closed = True
            worker.cancel()
            await asyncio.gather(worker, return_exceptions=True)
            if conn.session is not None:
                conn.session.cancel()  # disconnect cancels without sending
            if conn.watcher is not None:
                await asyncio.gather(conn.watcher, return_exceptions=True)
            self._release(conn)
            self._conns.discard(conn)

    async def _send_json(self, conn: _Conn, payload: dict[str, Any]) -> None:
        if conn.closed:
            return
        try:
            await conn.ws.send(json.dumps(payload))
        except ConnectionClosed:
            conn.closed = True

    async def _send_audio(self, conn: _Conn, f: AudioFrame) -> None:
        await conn.ws.send(encode_frame(f.request_id, f.sequence, f.pcm, last=f.last))

    async def _send_error(
        self, conn: _Conn, err: VoxStreamError, request_id: str | None = None
    ) -> None:
        await self._send_json(conn, msg.error(err, request_id))

    async def _reader(self, conn: _Conn) -> None:
        async for raw in conn.ws:
            try:
                if isinstance(raw, bytes):
                    raise VoxStreamError(
                        ErrorCode.MALFORMED_MESSAGE, "Binary frames are not accepted from clients."
                    )
                parsed = msg.parse_client_message(raw)
            except VoxStreamError as err:
                await self._send_error(conn, err)
                continue
            if isinstance(parsed, msg.CancelMsg) and (
                conn.session is not None or conn.inbox.empty()
            ):
                await self._on_cancel(conn, parsed)  # immediate, never queued behind text
                continue
            await conn.inbox.put(parsed)  # bounded: a full inbox stops socket reads

    async def _worker(self, conn: _Conn) -> None:
        while True:
            parsed = await conn.inbox.get()
            try:
                await self._dispatch(conn, parsed)
            except VoxStreamError as err:
                await self._send_error(conn, err)
            except Exception as exc:
                logger.error("unexpected failure: %s", type(exc).__name__)
                await self._send_error(conn, map_exception(exc))

    async def _dispatch(self, conn: _Conn, m: msg.AnyClientMessage) -> None:
        if isinstance(m, msg.StartMsg):
            await self._on_start(conn, m)
        elif isinstance(m, msg.TextMsg | msg.EndMsg):
            await self._on_text_or_end(conn, m)
        elif isinstance(m, msg.CancelMsg):
            await self._on_cancel(conn, m)
        else:
            await self._on_capabilities(conn)

    # -- message handlers ---------------------------------------------------------------------

    def _release(self, conn: _Conn) -> None:
        if conn.release is not None:
            release, conn.release = conn.release, None
            release()

    async def _on_start(self, conn: _Conn, m: msg.StartMsg) -> None:
        if conn.session is not None:
            raise VoxStreamError(
                ErrorCode.BUSY, "This connection already has an active request.", retryable=True
            )
        opened = await self.service.open_session(
            m.engine, m.voice, m.language, lambda f: self._send_audio(conn, f)
        )
        session = opened.session
        conn.release = opened.release
        conn.session = session
        conn.last_cancelled = None
        info = opened.info
        descriptor = msg.StreamDescriptor(
            frame_ms=info.frame_ms,
            voice=info.voice,
            engine=info.engine,
            language=info.language,
            streaming_mode=info.streaming_mode,
            execution_provider=info.execution_provider,
        )
        await self._send_json(conn, msg.started(str(session.request_id), descriptor))
        session.start()
        conn.watcher = asyncio.create_task(self._watch_request(conn, session))

    async def _on_text_or_end(self, conn: _Conn, m: msg.TextMsg | msg.EndMsg) -> None:
        session = conn.session
        if session is None or session.cancelled:
            if m.request_id == conn.last_cancelled:
                return  # input for a cancelled request is ignored
            raise VoxStreamError(ErrorCode.NO_ACTIVE_REQUEST, "No request is open; send 'start'.")
        if m.request_id != str(session.request_id):
            raise VoxStreamError(
                ErrorCode.REQUEST_MISMATCH, "request_id does not match the active request."
            )
        try:
            if isinstance(m, msg.TextMsg):
                await session.feed(m.text)
            else:
                await session.end()
        except VoxStreamError as err:
            if err.code in _FAIL_REQUEST_CODES:
                session.fail(err)  # terminal: the watcher sends the error
            elif session.cancelled:
                return
            else:
                raise

    async def _on_cancel(self, conn: _Conn, m: msg.CancelMsg) -> None:
        session = conn.session
        if session is None:
            if m.request_id == conn.last_cancelled:
                return
            raise_err = VoxStreamError(ErrorCode.NO_ACTIVE_REQUEST, "No request is open.")
            await self._send_error(conn, raise_err)
            return
        if m.request_id != str(session.request_id):
            await self._send_error(
                conn,
                VoxStreamError(
                    ErrorCode.REQUEST_MISMATCH, "request_id does not match the active request."
                ),
            )
            return
        conn.last_cancelled = m.request_id
        session.cancel()

    async def _on_capabilities(self, conn: _Conn) -> None:
        if conn.session is not None:
            raise VoxStreamError(
                ErrorCode.BUSY,
                "Capabilities can only be requested when no request is active.",
                retryable=True,
            )
        caps = self.service.capabilities()
        await self._send_json(
            conn,
            {
                "type": "capabilities",
                "engine": caps.name,
                "version": caps.version,
                "languages": caps.languages,
                "voices": caps.voices,
                "audio_format": {
                    "encoding": caps.audio_format.encoding,
                    "sample_rate": caps.audio_format.sample_rate,
                    "channels": caps.audio_format.channels,
                },
                "streaming_mode": caps.streaming_mode,
                "supports_cancel": caps.supports_cancel,
                "execution_provider": caps.execution_provider,
                "memory_notes": caps.memory_notes,
            },
        )

    async def _watch_request(self, conn: _Conn, session: Session) -> None:
        result = await session.wait()
        rid = str(session.request_id)
        if conn.session is session:
            conn.session = None
        self._release(conn)
        if conn.closed:
            return
        if result.state == "COMPLETED":
            payload = msg.completed(
                rid, result.audio_frames, result.audio_ms, result.chars, result.timing.to_dict()
            )
        elif result.state == "CANCELLED":
            payload = msg.cancelled(rid, result.audio_frames)
        else:
            assert result.error is not None
            payload = msg.error(result.error, rid)
        await self._send_json(conn, payload)
