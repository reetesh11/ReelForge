"""Cast helpers: prompts, mock bible line, upload sniffing and the backend resolver."""

from __future__ import annotations

import asyncio
import json
import socket
import struct
import threading
import zlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

import pytest

from reelforge.adapters.base import AdapterError
from reelforge.adapters.drawthings import DrawThingsAdapter
from reelforge.adapters.mflux import MfluxAdapter
from reelforge.adapters.mock_llm import MockLlm
from reelforge.cast.backends import probe_backend, resolve_image_adapter
from reelforge.cast.prompts import bible_messages, bible_schema, image_prompt
from reelforge.cast.uploads import NotAnImage, TooLarge, sniff_image
from reelforge.config import Settings
from reelforge.context import AppContext


def _png(w: int, h: int) -> bytes:
    def chunk(tag: bytes, data: bytes) -> bytes:
        body = tag + data
        return struct.pack(">I", len(data)) + body + struct.pack(">I", zlib.crc32(body))

    raw = (b"\x00" + b"\x10\x20\x30" * w) * h
    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0))
        + chunk(b"IDAT", zlib.compress(raw))
        + chunk(b"IEND", b"")
    )


def _jpeg(w: int, h: int) -> bytes:
    app0 = b"\xff\xe0" + struct.pack(">H", 16) + b"JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00"
    sof = b"\xff\xc0" + struct.pack(">HBHHB", 11, 8, h, w, 1) + b"\x01\x11\x00"
    return b"\xff\xd8" + app0 + sof + b"\xff\xda\x00\x02\xff\xd9"


def test_sniff_accepts_png_and_jpeg():
    assert sniff_image(_png(8, 16)) == ("png", 8, 16)
    assert sniff_image(_jpeg(32, 64)) == ("jpg", 32, 64)


@pytest.mark.parametrize(
    "data",
    [b"hello, this is text", b"", b"\x89PNG\r\n\x1a\n" + b"junk", b"\xff\xd8\xff", _png(2, 2)[:20]],
)
def test_sniff_rejects_non_images(data):
    with pytest.raises(NotAnImage):
        sniff_image(data)


def test_sniff_rejects_huge_dimensions():
    with pytest.raises(TooLarge):
        sniff_image(_jpeg(9000, 10))


def test_prompts_and_mock_bible_line():
    msgs = bible_messages("Tamatar", "round red tomato", "pixar")
    assert "bible_line" in bible_schema()["properties"]
    out = asyncio.run(MockLlm().chat(msgs, schema=bible_schema()))
    line = json.loads(out)["bible_line"]
    assert line == "Character: Tamatar. Look: round red tomato."
    prompt = image_prompt(line, "pixar")
    assert "Tamatar" in prompt and "9:16" in prompt and "plain background" in prompt


def _ctx(tmp_path: Path, **over: Any) -> AppContext:
    from reelforge.doctor import DoctorReport

    return AppContext.create(
        Settings(data_root=tmp_path / "data", **over), doctor=lambda: DoctorReport(checks=[])
    )


async def test_resolver_combinations(tmp_path):
    class H(BaseHTTPRequestHandler):
        def log_message(self, *a: Any) -> None:
            return

        def do_GET(self) -> None:  # noqa: N802
            self.send_response(200)
            self.send_header("Content-Length", "0")
            self.end_headers()

    httpd = ThreadingHTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    up = f"http://127.0.0.1:{httpd.server_address[1]}"
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    down = f"http://127.0.0.1:{s.getsockname()[1]}"
    s.close()
    cmd = tmp_path / "mflux"
    try:
        mock = _ctx(tmp_path / "a", drawthings_url=down)
        assert await resolve_image_adapter(mock) is mock.adapter
        assert (await probe_backend(mock)).as_dict()["kind"] == "mock"

        real_up = _ctx(tmp_path / "b", backend="real", drawthings_url=up)
        assert isinstance(await resolve_image_adapter(real_up), DrawThingsAdapter)
        assert (await probe_backend(real_up)).reachable is True

        both = {"backend": "real", "image_fallback": "mflux", "mflux_command": cmd}
        down_mflux = _ctx(tmp_path / "c", drawthings_url=down, **both)
        assert isinstance(await resolve_image_adapter(down_mflux), MfluxAdapter)
        assert (await probe_backend(down_mflux)).mflux_available is True

        down_none = _ctx(tmp_path / "d", backend="real", drawthings_url=down)
        assert isinstance(await resolve_image_adapter(down_none), DrawThingsAdapter)
        status = await probe_backend(down_none)
        assert status.reachable is False and status.mflux_available is False
        with pytest.raises(AdapterError):
            await resolve_image_adapter(down_none, "mflux")

        up_mflux = _ctx(tmp_path / "e", drawthings_url=up, **both)
        assert isinstance(await resolve_image_adapter(up_mflux), DrawThingsAdapter)
        assert isinstance(await resolve_image_adapter(up_mflux, "mflux"), MfluxAdapter)
    finally:
        httpd.shutdown()
        httpd.server_close()
