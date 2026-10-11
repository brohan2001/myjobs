import socket

import pytest

from tests.characterization.conftest import NetworkAccessError


def test_network_guard_blocks_sockets():
    with pytest.raises(NetworkAccessError):
        socket.create_connection(("example.com", 80))
    s = socket.socket()
    try:
        with pytest.raises(NetworkAccessError):
            s.connect(("127.0.0.1", 9))
    finally:
        s.close()


def test_network_guard_blocks_dns():
    with pytest.raises(NetworkAccessError):
        socket.getaddrinfo("example.com", 80)
