"""AC-10: media path confinement, loopback-only binding, no shell use."""

from __future__ import annotations

import re
import subprocess

import pytest
from rf_helpers import (
    REPO_ROOT,
    UpProcess,
    create_project,
    free_port,
    make_client,
    make_ctx,
    make_settings,
    store_bytes,
)


def _media_setup(tmp_path):
    ctx = make_ctx(make_settings(tmp_path))
    client = make_client(ctx, start_worker=False)
    client.__enter__()
    pid = create_project(client)["id"]
    _, art = store_bytes(ctx, pid, b"inside-bytes")
    return ctx, client, art


def _repoint(ctx, art, new_path: str):
    from reelforge.db.models import Artifact
    from sqlalchemy import update

    with ctx.session_factory() as s, s.begin():
        s.execute(update(Artifact).where(Artifact.id == art.id).values(path=new_path))


def test_media_dotdot_escape_is_forbidden(tmp_path):
    ctx, client, art = _media_setup(tmp_path)
    secret = tmp_path / "secret.txt"
    secret.write_text("TOP-SECRET")
    _repoint(ctx, art, "../secret.txt")
    r = client.get(f"/media/{art.id}")
    assert r.status_code == 403
    assert r.json() == {"detail": "path outside data root"}
    assert b"TOP-SECRET" not in r.content
    client.__exit__(None, None, None)
    ctx.close()


def test_media_symlink_escape_is_forbidden(tmp_path):
    ctx, client, art = _media_setup(tmp_path)
    secret = tmp_path / "secret.txt"
    secret.write_text("TOP-SECRET")
    link = ctx.settings.data_root / "link.txt"
    link.symlink_to(secret)
    _repoint(ctx, art, "link.txt")
    r = client.get(f"/media/{art.id}")
    assert r.status_code == 403 and b"TOP-SECRET" not in r.content
    r = client.get(f"/media/{art.id}", headers={"Range": "bytes=0-3"})
    assert r.status_code == 403
    client.__exit__(None, None, None)
    ctx.close()


def test_media_unknown_and_missing_file(tmp_path):
    ctx, client, art = _media_setup(tmp_path)
    r = client.get("/media/01ARZ3NDEKTSV4RRFFQ69G5FAV")
    assert r.status_code == 404 and r.json() == {"detail": "artifact not found"}
    ctx.store.absolute_path(art).unlink()
    r = client.get(f"/media/{art.id}")
    assert r.status_code == 404 and r.json() == {"detail": "file missing"}
    client.__exit__(None, None, None)
    ctx.close()


def test_inside_file_is_served(tmp_path):
    ctx, client, art = _media_setup(tmp_path)
    r = client.get(f"/media/{art.id}")
    assert r.status_code == 200 and r.content == b"inside-bytes"
    client.__exit__(None, None, None)
    ctx.close()


def test_settings_reject_non_loopback_hosts(tmp_path):
    from pydantic import ValidationError
    from reelforge.config import Settings

    assert Settings(data_root=tmp_path).host == "127.0.0.1"
    for bad in ("0.0.0.0", "localhost", "::", "10.0.0.2"):
        with pytest.raises(ValidationError):
            Settings(data_root=tmp_path, host=bad)
    with pytest.raises(ValidationError):
        Settings(data_root=tmp_path, api_port=0)
    with pytest.raises(ValidationError):
        Settings(data_root=tmp_path, ui_port=65536)


def test_server_listens_on_loopback_only(tmp_path):
    port = free_port()
    up = UpProcess(tmp_path / "data", port)
    try:
        up.wait_ready()
        out = subprocess.run(  # noqa: PLW1510
            ["lsof", "-nP", f"-iTCP:{port}", "-sTCP:LISTEN"],
            capture_output=True,
            text=True,
            timeout=20,
        ).stdout
        assert f"127.0.0.1:{port}" in out
        assert f"*:{port}" not in out and f"0.0.0.0:{port}" not in out
    finally:
        up.stop()


def test_no_shell_true_in_sources():
    pattern = re.compile(r"shell\s*=\s*True|os\.system\(|os\.popen\(")
    src = REPO_ROOT / "src"
    assert list(src.rglob("*.py")), "src/reelforge must exist"
    hits = []
    for base in (src, REPO_ROOT / "tests", REPO_ROOT / "scripts"):
        if not base.exists():
            continue
        for f in base.rglob("*.py"):
            for n, line in enumerate(f.read_text(errors="ignore").splitlines(), 1):
                if pattern.search(line) and "pattern = re.compile" not in line:
                    hits.append(f"{f.relative_to(REPO_ROOT)}:{n}")
    assert hits == []
