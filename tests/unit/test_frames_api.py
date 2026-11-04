from __future__ import annotations

from _helpers import make_client, make_ctx


def test_unknown_project_is_404_and_locked_project_is_409(tmp_path):
    ctx = make_ctx(tmp_path)
    with make_client(ctx) as client:
        assert client.get("/api/v1/projects/nope/frames").status_code == 404
        pid = client.post("/api/v1/projects", json={"title": "T"}).json()["id"]
        r = client.get(f"/api/v1/projects/{pid}/frames")
        assert r.status_code == 409 and r.json() == {"detail": "Approve the voices first."}
        r = client.post(f"/api/v1/projects/{pid}/frames:generate", json={"mode": "missing"})
        assert r.status_code == 409
        r = client.post(f"/api/v1/projects/{pid}/frames:cancel")
        assert r.status_code == 409
