"""Acceptance-suite fixtures. Blocks all outbound (non-loopback) network (AC-12)."""

from __future__ import annotations

import ipaddress
import socket

import pytest

_LOOPBACK_NAMES = {"localhost", "127.0.0.1", "::1", ""}


def _is_loopback(host: object) -> bool:
    if isinstance(host, bytes):
        host = host.decode()
    if not isinstance(host, str):
        return True
    if host in _LOOPBACK_NAMES:
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


@pytest.fixture(autouse=True)
def _block_outbound_network(monkeypatch: pytest.MonkeyPatch) -> None:
    real_connect = socket.socket.connect
    real_connect_ex = socket.socket.connect_ex

    def guard(address: object) -> None:
        if isinstance(address, tuple) and address and not _is_loopback(address[0]):
            raise AssertionError(f"outbound network blocked: {address!r}")

    def connect(self: socket.socket, address: object) -> None:
        guard(address)
        return real_connect(self, address)  # type: ignore[arg-type]

    def connect_ex(self: socket.socket, address: object) -> int:
        guard(address)
        return real_connect_ex(self, address)  # type: ignore[arg-type]

    monkeypatch.setattr(socket.socket, "connect", connect)
    monkeypatch.setattr(socket.socket, "connect_ex", connect_ex)
