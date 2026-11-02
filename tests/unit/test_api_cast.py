"""Cast routes: guards, duplicate jobs, uploads, approve/reopen stage rules."""

from __future__ import annotations

import struct
import time
import zlib

import yaml_samples as ys
from _helpers import make_client, make_ctx


def _png(w: int = 8, h: int = 16) -> bytes:
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


def _project(client, approve: bool = True) -> str:
    pid = client.post("/api/v1/projects", json={"title": "T"}).json()["id"]
    if approve:
        client.put(
            f"/api/v1/projects/{pid}/story",
            content=ys.STORY.encode(),
            headers={"Content-Type": "text/plain"},
        )
        assert client.post(f"/api/v1/projects/{pid}/story:approve").status_code == 200
    return pid


def _wait(ctx, job_id: str):
    deadline = time.monotonic() + 20
    while time.monotonic() < deadline:
        job = ctx.queue.get(job_id)
        if job.status in {"succeeded", "failed", "cancelled"}:
            return job
        time.sleep(0.03)
    raise AssertionError("job stuck")


def test_guards_before_story_approval_and_unknowns(tmp_path):
    ctx = make_ctx(tmp_path)
    with make_client(ctx, start_worker=False) as c:
        draft = _project(c, approve=False)
        for method, url in (
            ("get", f"/api/v1/projects/{draft}/cast"),
            ("post", f"/api/v1/projects/{draft}/cast/tomato:reopen"),
        ):
            r = getattr(c, method)(url)
            assert r.status_code == 409 and r.json() == {"detail": "Approve the story first."}
        pid = _project(c)
        assert c.post(f"/api/v1/projects/{pid}/cast/ghost:reopen").status_code == 404
        r = c.post(f"/api/v1/projects/{pid}/cast/tomato:use-library", json={"character_id": "nope"})
        assert r.status_code == 404
        assert c.post(
            f"/api/v1/projects/{pid}/cast/tomato:approve", json={"candidate_id": "x"}
        ).json() == {"detail": "candidate not found"}


def test_duplicate_generate_returns_same_job(tmp_path):
    ctx = make_ctx(tmp_path)
    with make_client(ctx, start_worker=False) as c:
        pid = _project(c)
        url = f"/api/v1/projects/{pid}/cast/tomato:generate"
        a = c.post(url, json={"seed": 1})
        b = c.post(url, json={"seed": 99})
        assert a.status_code == b.status_code == 202
        assert a.json()["id"] == b.json()["id"]
        assert a.json()["heavy"] is True and a.json()["payload"]["total"] == 4
        item = c.get(f"/api/v1/projects/{pid}/cast").json()["characters"][0]
        assert item["state"] == "generating" and item["job_id"] == a.json()["id"]


def test_upload_accepts_png_by_content_and_rejects_text(tmp_path):
    ctx = make_ctx(tmp_path, max_upload_mb=1)
    with make_client(ctx, start_worker=False) as c:
        pid = _project(c)
        url = f"/api/v1/projects/{pid}/cast/tomato:upload"
        r = c.post(url, files={"file": ("x.txt", _png(), "text/plain")})
        assert r.status_code == 201 and r.json()["candidates"][0]["kind"] == "upload"
        assert r.json()["candidates"][0]["width"] == 8
        bad = c.post(url, files={"file": ("x.png", b"plain text", "image/png")})
        assert bad.status_code == 415
        big = c.post(url, files={"file": ("x.png", _png() + b"0" * 1_100_000, "image/png")})
        assert big.status_code == 413
        assert len(c.get(f"/api/v1/projects/{pid}/cast").json()["characters"][0]["candidates"]) == 1


def test_approve_upload_then_reopen_moves_stage(tmp_path):
    ctx = make_ctx(tmp_path)
    with make_client(ctx) as c:
        pid = _project(c)
        for key in ("tomato",):
            up = c.post(
                f"/api/v1/projects/{pid}/cast/{key}:upload", files={"file": ("a.png", _png())}
            )
            cid = up.json()["candidates"][0]["id"]
            r = c.post(f"/api/v1/projects/{pid}/cast/{key}:approve", json={"candidate_id": cid})
            assert r.status_code == 200, r.text
        assert r.json()["project_stage"] == "CAST_APPROVED"
        assert r.json()["character"]["state"] == "approved"
        r = c.post(f"/api/v1/projects/{pid}/cast/tomato:reopen")
        assert r.json()["project_stage"] == "STORY_APPROVED"
        assert r.json()["character"]["approved"] is False
        assert len(c.get("/api/v1/library/characters").json()) == 1


def test_refine_requires_known_candidate(tmp_path):
    ctx = make_ctx(tmp_path)
    with make_client(ctx, start_worker=False) as c:
        pid = _project(c)
        r = c.post(
            f"/api/v1/projects/{pid}/cast/tomato:generate",
            json={"refine": {"from_candidate": "nope", "instruction": "x"}},
        )
        assert r.status_code == 404
