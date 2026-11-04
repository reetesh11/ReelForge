"""Exported reels and covers are served with ranges and stay inside the data root."""

from __future__ import annotations

from pathlib import Path

import pytest
from _helpers import make_client, make_ctx

from reelforge.assembly.jobs import register_file
from reelforge.db.models import Artifact


@pytest.fixture
def served(tmp_path: Path):
    ctx = make_ctx(tmp_path)
    with make_client(ctx, start_worker=False) as c:
        pid = c.post("/api/v1/projects", json={"title": "T"}).json()["id"]
        folder = ctx.settings.data_root / "projects" / "reels"
        folder.mkdir(parents=True)
        reel = folder / "final.mp4"
        reel.write_bytes(bytes(range(200)))
        cover = folder / "cover.jpg"
        cover.write_bytes(b"\xff\xd8" + b"x" * 30)
        yield ctx, c, pid, reel, cover, tmp_path
    ctx.close()


def _register(ctx, pid, kind, path):
    return register_file(ctx, pid, kind, path, job_id=None, inputs=[])


def test_reel_ranges(served) -> None:
    ctx, c, pid, reel, _, _ = served
    art = _register(ctx, pid, "final", reel)
    r = c.get(f"/media/{art.id}", headers={"Range": "bytes=0-99"})
    assert r.status_code == 206 and len(r.content) == 100
    assert r.headers["content-range"] == "bytes 0-99/200"
    assert r.headers["content-type"] == "video/mp4" and r.headers["accept-ranges"] == "bytes"
    assert c.get(f"/media/{art.id}", headers={"Range": "bytes=500-"}).status_code == 416
    r = c.get(f"/media/{art.id}", headers={"Range": "bytes=nope"})
    assert r.status_code == 200 and len(r.content) == 200


def test_cover_is_served_as_jpeg(served) -> None:
    ctx, c, pid, _, cover, _ = served
    art = _register(ctx, pid, "cover", cover)
    r = c.get(f"/media/{art.id}")
    assert r.status_code == 200 and r.headers["content-type"] == "image/jpeg"


def test_paths_outside_the_data_root_are_refused(served) -> None:
    ctx, c, pid, reel, _, tmp_path = served
    art = _register(ctx, pid, "final", reel)
    secret = tmp_path / "secret.txt"
    secret.write_text("top secret")
    with ctx.session_factory.begin() as s:
        row = s.get(Artifact, art.id)
        assert row is not None
        row.path = "../secret.txt"
    r = c.get(f"/media/{art.id}")
    assert r.status_code == 403 and b"top secret" not in r.content


def test_symlink_escape_is_refused(served) -> None:
    ctx, c, pid, reel, _, tmp_path = served
    secret = tmp_path / "secret.mp4"
    secret.write_bytes(b"top secret")
    link = reel.with_name("link.mp4")
    link.symlink_to(secret)
    with ctx.session_factory.begin() as s:
        row = Artifact(
            project_id=pid, owner_type="project", owner_id=pid, kind="final", take_no=1,
            path=link.relative_to(ctx.settings.data_root).as_posix(), sha256="0", inputs_fp="0",
            prompt="", version="1", model_key="ffmpeg", seed=0,
        )  # fmt: skip
        s.add(row)
        s.flush()
        rid = row.id
    r = c.get(f"/media/{rid}")
    assert r.status_code == 403 and b"top secret" not in r.content
