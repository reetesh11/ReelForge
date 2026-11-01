"""Story routes: status codes and bodies."""

from __future__ import annotations

import yaml_samples as ys
from _helpers import make_client, make_ctx


def _put(c, pid: str, text: str):
    return c.put(
        f"/api/v1/projects/{pid}/story",
        content=text.encode(),
        headers={"Content-Type": "text/plain"},
    )


def test_routes(tmp_path):
    ctx = make_ctx(tmp_path)
    with make_client(ctx, start_worker=False) as c:
        pid = c.post("/api/v1/projects", json={"title": "T"}).json()["id"]
        base = f"/api/v1/projects/{pid}"
        assert c.get(f"{base}/story").json() == {"detail": "no story yet"}
        assert c.get(f"{base}/story/export").status_code == 404
        assert c.get(f"{base}/story/versions").json() == []
        assert c.get(f"{base}/story/versions/1").json() == {"detail": "version not found"}
        r = _put(c, pid, ys.STORY)
        assert r.status_code == 200 and r.json()["affected"] == []
        got = c.get(f"{base}/story").json()
        assert got["yaml_text"] == ys.STORY and got["version"] == 1
        assert c.get(f"{base}/story/export").content == ys.STORY.encode()
        imp = c.post(
            f"{base}/story:import",
            content=ys.STORY.encode(),
            headers={"Content-Type": "text/plain"},
        )
        assert imp.status_code == 201 and imp.json()["version"] == 2
        vs = c.get(f"{base}/story/versions").json()
        assert [v["version"] for v in vs] == [2, 1] and "yaml_text" not in vs[0]
        assert c.post(f"{base}/story:approve").json()["stage"] == "STORY_APPROVED"
        assert c.get(f"{base}/stale").json() == {"items": []}
        assert c.get("/api/v1/story/schema").json()["title"] == "Story"


def test_errors(tmp_path):
    ctx = make_ctx(tmp_path)
    with make_client(ctx, start_worker=False) as c:
        pid = c.post("/api/v1/projects", json={"title": "T"}).json()["id"]
        r = _put(c, pid, ys.STORY + "foo: 1\n")
        assert r.status_code == 422
        assert r.json()["detail"] == "story.yaml is invalid"
        assert r.json()["errors"][0] == {
            "path": "foo",
            "message": "unknown field",
            "line": None,
            "column": None,
        }
        assert _put(c, pid, "#" * 1_048_577).status_code == 413
        assert c.post(f"/api/v1/projects/{pid}/story:approve").status_code == 409
        r = c.put(
            f"/api/v1/projects/{pid}/story",
            content=b"\xff\xfe",
            headers={"Content-Type": "text/plain"},
        )
        assert r.status_code == 422
        assert _put(c, "nope", ys.STORY).status_code == 404
