"""Content sniffing for uploaded character images (PNG or JPEG only)."""

from __future__ import annotations

import struct

MAX_SIDE_PX = 8192
_PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
_JPEG_SOF = {*range(0xC0, 0xC4), *range(0xC5, 0xC8), *range(0xC9, 0xCC), *range(0xCD, 0xD0)}
_NO_LENGTH = {0x01, 0xD8, 0xD9, *range(0xD0, 0xD8)}


class NotAnImage(ValueError):
    pass


class TooLarge(ValueError):
    pass


def _png_size(data: bytes) -> tuple[int, int]:
    if len(data) < 33 or data[12:16] != b"IHDR":
        raise NotAnImage("no PNG header")
    width, height = struct.unpack(">II", data[16:24])
    return width, height


def _jpeg_size(data: bytes) -> tuple[int, int]:
    pos = 2
    while pos + 4 <= len(data):
        if data[pos] != 0xFF:
            raise NotAnImage("bad JPEG marker")
        marker = data[pos + 1]
        if marker == 0xFF:
            pos += 1
            continue
        if marker in _NO_LENGTH:
            pos += 2
            continue
        (length,) = struct.unpack(">H", data[pos + 2 : pos + 4])
        if marker in _JPEG_SOF:
            if length < 8 or pos + 9 > len(data):
                raise NotAnImage("truncated JPEG header")
            height, width = struct.unpack(">HH", data[pos + 5 : pos + 9])
            return width, height
        if marker == 0xDA:
            break
        pos += 2 + length
    raise NotAnImage("no JPEG frame header")


def sniff_image(data: bytes) -> tuple[str, int, int]:
    """Return (ext, width, height) judged by content; raise NotAnImage or TooLarge."""
    if data.startswith(_PNG_SIGNATURE):
        ext, (width, height) = "png", _png_size(data)
    elif data.startswith(b"\xff\xd8\xff"):
        ext, (width, height) = "jpg", _jpeg_size(data)
    else:
        raise NotAnImage("not a PNG or JPEG")
    if width < 1 or height < 1:
        raise NotAnImage("empty image")
    if width > MAX_SIDE_PX or height > MAX_SIDE_PX:
        raise TooLarge(f"{width}x{height}")
    return ext, width, height
