"""Composition root: one shared service feeding every enabled transport."""

from __future__ import annotations

from typing import Any

from voxstream.config import Settings
from voxstream.core.admission import AdmissionController
from voxstream.core.service import VoxStreamService
from voxstream.engines.base import TTSEngine


class VoxStreamApp:
    def __init__(self, settings: Settings, engine: TTSEngine) -> None:
        self.settings = settings
        self.engine = engine
        self.service = VoxStreamService(settings, engine)
        self._ws: Any = None
        self._grpc: Any = None
        self._health: Any = None
        self.transport = "websocket"  # which transport test clients use (tests only)

    @property
    def admission(self) -> AdmissionController:
        return self.service.admission

    @property
    def port(self) -> int:
        """The HTTP port: WebSocket + health, or the standalone health listener."""
        server = self._ws or self._health
        assert server is not None, "no HTTP listener is running"
        return int(server.port)

    @property
    def grpc_port(self) -> int:
        assert self._grpc is not None, "gRPC is not enabled"
        return int(self._grpc.port)

    async def start(self) -> None:
        self.settings.validate_transports()
        self.settings.validate_bind()
        try:
            if self.settings.enable_websocket:
                from voxstream.transports.websocket.server import VoxStreamServer

                self._ws = VoxStreamServer(self.service)
                await self._start_http(self._ws)
            else:
                from voxstream.transports.health import HealthServer

                self._health = HealthServer(self.service, self.settings.host, self.settings.port)
                await self._start_http(self._health)
            if self.settings.enable_grpc:
                from voxstream.transports.grpc.server import GrpcServer

                self._grpc = GrpcServer(self.service)
                await self._grpc.start()
        except BaseException:
            await self._close_transports()
            raise

    async def _start_http(self, server: Any) -> None:
        try:
            await server.start()
        except OSError as exc:
            raise OSError(
                f"Could not bind the HTTP/WebSocket listener to "
                f"{self.settings.host}:{self.settings.port} ({exc.strerror or exc}). "
                "Is the port already in use? Set VOXSTREAM_PORT to a free port."
            ) from exc

    async def _close_transports(self) -> None:
        for server in (self._grpc, self._ws, self._health):
            if server is not None:
                await server.close()
        self._grpc = self._ws = self._health = None

    async def close(self) -> None:
        await self._close_transports()
        await self.engine.stop()

    async def __aenter__(self) -> VoxStreamApp:
        await self.start()
        return self

    async def __aexit__(self, *exc: object) -> None:
        await self.close()
