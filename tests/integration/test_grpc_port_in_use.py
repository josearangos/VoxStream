import socket

import pytest

from helpers import make_settings
from voxstream.app import VoxStreamApp
from voxstream.engines.mock import MockEngine


async def test_startup_error_names_grpc_port_setting():
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        sock.listen()
        busy = sock.getsockname()[1]
        app = VoxStreamApp(make_settings(grpc_port=busy), MockEngine())
        with pytest.raises(OSError, match="VOXSTREAM_GRPC_PORT"):
            await app.start()
