from __future__ import annotations

import struct
import zlib

from _helpers import make_ctx

from reelforge.db.models import Project
from reelforge.frames.product import locate_product, resolve_product
from reelforge.story.schema import Character, Product, Scene, Story


def _png(width: int = 4, height: int = 4) -> bytes:
    def chunk(tag: bytes, data: bytes) -> bytes:
        body = tag + data
        return struct.pack(">I", len(data)) + body + struct.pack(">I", zlib.crc32(body))

    raw = (b"\x00" + b"\x10\x20\x30" * width) * height
    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
        + chunk(b"IDAT", zlib.compress(raw))
        + chunk(b"IEND", b"")
    )


def _story(asset: str | None) -> Story:
    return Story(
        version=1,
        title="t",
        language="english",
        style="3D",
        aspect="9:16",
        fps=24,
        target_seconds=10,
        characters={"a": Character(name="A", look="l")},
        scenes=[Scene(id="s1", action="x")],
        product=Product(name="Pack", asset=asset),
    )


def _project(ctx) -> str:
    with ctx.session_factory.begin() as s:
        p = Project(slug="t", title="T", data_dir="projects/p")
        s.add(p)
        s.flush()
        return p.id


def test_asset_under_data_root_is_registered_once(tmp_path):
    ctx = make_ctx(tmp_path)
    pid = _project(ctx)
    pack = ctx.settings.data_root / "pack.png"
    pack.write_bytes(_png())
    story = _story(str(pack))
    first = resolve_product(ctx, pid, story)
    second = resolve_product(ctx, pid, story)
    assert first is not None and second is not None and first.id == second.id
    rel = _story("pack.png")  # relative paths resolve against the data root
    assert locate_product(ctx, rel) is not None


def test_missing_outside_and_non_image_are_none(tmp_path):
    ctx = make_ctx(tmp_path)
    pid = _project(ctx)
    outside = tmp_path / "elsewhere.png"
    outside.write_bytes(_png())
    text = ctx.settings.data_root / "pack.txt"
    text.write_text("not an image")
    assert resolve_product(ctx, pid, _story(str(ctx.settings.data_root / "none.png"))) is None
    assert resolve_product(ctx, pid, _story(str(outside))) is None
    assert resolve_product(ctx, pid, _story(str(text))) is None
    assert resolve_product(ctx, pid, _story(None)) is None
