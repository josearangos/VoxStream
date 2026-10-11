"""gRPC transport: one bidirectional ``Stream`` call per synthesis request."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from typing import Any

from grpc import aio

from voxstream.core.frames import AudioFrame
from voxstream.core.service import OpenedSession, VoxStreamService
from voxstream.core.session import Session, SessionResult, map_exception
from voxstream.errors import ErrorCode, VoxStreamError
from voxstream.logging import logger, transport_var
from voxstream.transports.grpc import convert
from voxstream.transports.grpc.gen import voxstream_pb2 as pb
from voxstream.transports.grpc.gen import voxstream_pb2_grpc as pb_grpc

OUTBOX_SIZE = 8
INBOX_SIZE = 8
MAX_MESSAGE_BYTES = 64 * 1024
_FAIL_REQUEST_CODES = (ErrorCode.TEXT_TOO_LONG, ErrorCode.EMPTY_REQUEST)
_GRACE_S = 1.0


def _event(**kw: Any) -> pb.ServerEvent:
    return pb.ServerEvent(**kw)


class _Call:
    """State of one ``Stream`` call (one request per call)."""

    def __init__(self, service: VoxStreamService) -> None:
        self.service = service
        self.outbox: asyncio.Queue[pb.ServerEvent | None] = asyncio.Queue(OUTBOX_SIZE)
        self.inbox: asyncio.Queue[pb.ClientEvent] = asyncio.Queue(INBOX_SIZE)
        self.opened: OpenedSession | None = None
        self.session: Session | None = None
        self.ended = False  # the client sent End (or the request failed it)
        self.closing = False
        self.tasks: list[asyncio.Task[None]] = []

    # -- outbound ---------------------------------------------------------------------------

    async def send_audio(self, frame: AudioFrame) -> None:
        await self.outbox.put(_event(audio=convert.to_audio_chunk(frame)))

    async def send_error(self, err: VoxStreamError, request_id: str | None = None) -> None:
        await self.outbox.put(_event(error=convert.to_error(err, request_id)))

    async def finish_call(self) -> None:
        await self.outbox.put(None)

    def drop_queued_audio(self) -> None:
        kept: list[pb.ServerEvent] = []
        while not self.outbox.empty():
            ev = self.outbox.get_nowait()
            if ev is not None and ev.WhichOneof("event") != "audio":
                kept.append(ev)
        for ev in kept:
            self.outbox.put_nowait(ev)

    # -- inbound ----------------------------------------------------------------------------

    async def read(self, requests: AsyncIterator[pb.ClientEvent]) -> None:
        async for ev in requests:
            if self.closing:
                return
            case = ev.WhichOneof("event")
            if case is None:
                await self.send_error(
                    VoxStreamError(ErrorCode.MALFORMED_MESSAGE, "The event has no message set.")
                )
            elif case == "start":
                if not await self.on_start(ev.start):
                    return
            elif case == "cancel":
                await self.on_cancel(ev.cancel)
            elif self.session is None:
                await self.send_error(
                    VoxStreamError(ErrorCode.NO_ACTIVE_REQUEST, "No request is open; send 'start'.")
                )
            else:
                await self.inbox.put(ev)  # bounded: a full inbox stops reading from the call

    async def work(self) -> None:
        while True:
            ev = await self.inbox.get()
            try:
                await self.on_text_or_end(ev)
            except VoxStreamError as err:
                await self.send_error(err)
            except Exception as exc:
                logger.error("unexpected failure: %s", type(exc).__name__)
                await self.send_error(map_exception(exc))

    async def on_start(self, m: pb.Start) -> bool:
        """Open the request. Returns False when the call is over (rejected Start)."""
        if self.session is not None:
            await self.send_error(
                VoxStreamError(
                    ErrorCode.BUSY, "This call already has an active request.", retryable=True
                )
            )
            return True
        engine, voice, language = convert.from_start(m)
        try:
            opened = await self.service.open_session(engine, voice, language, self.send_audio)
        except Exception as exc:
            await self.send_error(map_exception(exc))
            await self.finish_call()
            return False
        self.opened = opened
        self.session = opened.session
        rid = str(opened.session.request_id)
        await self.outbox.put(_event(started=convert.to_started(rid, opened.info)))
        opened.session.start()
        self.tasks.append(asyncio.create_task(self.watch(opened.session)))
        return True

    def _check_id(self, session: Session, rid: str | None) -> None:
        if rid is not None and rid != str(session.request_id):
            raise VoxStreamError(
                ErrorCode.REQUEST_MISMATCH, "request_id does not match the active request."
            )

    async def on_text_or_end(self, ev: pb.ClientEvent) -> None:
        session = self.session
        assert session is not None
        if session.cancelled:
            return  # input for a cancelled request is ignored
        case = ev.WhichOneof("event")
        m = ev.text if case == "text" else ev.end
        self._check_id(session, convert.request_id_of(m))
        try:
            if case == "text":
                if self.ended:
                    raise VoxStreamError(
                        ErrorCode.NO_ACTIVE_REQUEST,
                        "No open request is accepting text on this connection.",
                    )
                await session.feed(ev.text.text)
            else:
                if self.ended:
                    return  # a repeated End is ignored
                self.ended = True
                await session.end()
        except VoxStreamError as err:
            if err.code in _FAIL_REQUEST_CODES:
                session.fail(err)  # terminal: the watcher sends the error
            elif session.cancelled:
                return
            else:
                raise

    async def on_cancel(self, m: pb.Cancel) -> None:
        session = self.session
        if session is None:
            await self.send_error(
                VoxStreamError(ErrorCode.NO_ACTIVE_REQUEST, "No request is open.")
            )
            return
        try:
            self._check_id(session, convert.request_id_of(m))
        except VoxStreamError as err:
            await self.send_error(err)
            return
        session.cancel()  # immediate, never queued behind text

    async def watch(self, session: Session) -> None:
        result: SessionResult = await session.wait()
        rid = str(session.request_id)
        self.closing = True
        if self.opened is not None:
            self.opened.release()  # free the slot before the client can see the terminal event
        if result.state == "COMPLETED":
            terminal = _event(completed=convert.to_completed(rid, result))
        elif result.state == "CANCELLED":
            self.drop_queued_audio()
            terminal = _event(cancelled=convert.to_cancelled(rid, result))
        else:
            assert result.error is not None
            terminal = _event(error=convert.to_error(result.error, rid))
        await self.outbox.put(terminal)
        await self.finish_call()

    # -- cleanup ----------------------------------------------------------------------------

    async def cleanup(self) -> None:
        self.closing = True
        if self.session is not None:
            self.session.cancel()  # idempotent; a client drop cancels without sending
        for task in self.tasks:
            task.cancel()
        await asyncio.gather(*self.tasks, return_exceptions=True)
        if self.opened is not None:
            self.opened.release()


class _Synthesizer(pb_grpc.SynthesizerServicer):
    def __init__(self, service: VoxStreamService) -> None:
        self.service = service

    async def Stream(
        self,
        request_iterator: AsyncIterator[pb.ClientEvent],
        context: aio.ServicerContext[Any, Any],
    ) -> AsyncIterator[pb.ServerEvent]:
        transport_var.set("grpc")
        call = _Call(self.service)
        reader = asyncio.create_task(self._read(call, request_iterator))
        worker = asyncio.create_task(call.work())
        call.tasks += [reader, worker]
        try:
            while True:
                ev = await call.outbox.get()
                if ev is None:
                    return
                yield ev
        finally:
            await call.cleanup()

    async def _read(self, call: _Call, requests: AsyncIterator[pb.ClientEvent]) -> None:
        try:
            await call.read(requests)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.error("gRPC read failure: %s", type(exc).__name__)
            if call.session is not None:
                call.session.fail(map_exception(exc))
            else:
                await call.send_error(map_exception(exc))
                await call.finish_call()

    async def GetCapabilities(
        self, request: pb.CapabilitiesRequest, context: aio.ServicerContext[Any, Any]
    ) -> pb.Capabilities:
        return convert.capabilities_to_proto(self.service.capabilities())


class GrpcServer:
    def __init__(self, service: VoxStreamService) -> None:
        self.service = service
        self.settings = service.settings
        self._server: aio.Server | None = None
        self._port = 0

    @property
    def port(self) -> int:
        return self._port

    async def start(self) -> None:
        self.settings.validate_bind()
        frame_bytes = 24000 * self.settings.frame_ms // 1000 * 2
        server = aio.server(
            options=[
                ("grpc.max_receive_message_length", MAX_MESSAGE_BYTES),
                ("grpc.max_send_message_length", frame_bytes + 1024),
                ("grpc.so_reuseport", 0),  # a busy port must fail instead of being shared
            ]
        )
        pb_grpc.add_SynthesizerServicer_to_server(  # type: ignore[no-untyped-call]
            _Synthesizer(self.service), server
        )
        address = f"{self.settings.host}:{self.settings.grpc_port}"
        try:
            self._port = server.add_insecure_port(address)
        except RuntimeError:
            self._port = 0
        if self._port == 0:
            raise OSError(
                f"Could not bind the gRPC server to {address}. Is the port already in use? "
                "Set VOXSTREAM_GRPC_PORT to a free port."
            )
        await server.start()
        self._server = server

    async def close(self) -> None:
        if self._server is not None:
            await self._server.stop(_GRACE_S)
            self._server = None
