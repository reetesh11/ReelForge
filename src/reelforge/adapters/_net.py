"""Loopback-only HTTP probing shared by the service adapters."""

from __future__ import annotations

import ipaddress
from urllib.parse import urlparse

import httpx

PROBE_TIMEOUT_S = 1.0


def is_loopback_url(url: str) -> bool:
    host = urlparse(url).hostname or ""
    if host == "localhost":
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


def probe(url: str, path: str = "") -> httpx.Response:
    """GET a loopback URL; raises ValueError for non-loopback targets, httpx errors otherwise."""
    if not is_loopback_url(url):
        raise ValueError(f"{url} is not a loopback address; refusing to connect")
    return httpx.get(url.rstrip("/") + path, timeout=PROBE_TIMEOUT_S, trust_env=False)
