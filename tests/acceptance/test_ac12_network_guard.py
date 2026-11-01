"""AC-12: the suite runs with outbound network blocked (guard lives in conftest.py)."""

from __future__ import annotations

import socket

import pytest


def test_non_loopback_connections_are_refused_by_the_guard():
    s = socket.socket()
    try:
        with pytest.raises(AssertionError, match="outbound network blocked"):
            s.connect(("93.184.216.34", 80))
    finally:
        s.close()


def test_loopback_connections_are_allowed():
    srv = socket.socket()
    srv.bind(("127.0.0.1", 0))
    srv.listen(1)
    c = socket.socket()
    try:
        c.connect(srv.getsockname())
    finally:
        c.close()
        srv.close()
