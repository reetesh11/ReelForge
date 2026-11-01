import time

from _helpers import make_client, make_ctx


def _body(**over):
    return {
        "owner_type": "c", "owner_id": "o", "kind": "candidate", "media": "image",
        "prompt": "p", "seed": 1, **over,
    }  # fmt: skip


def test_job_lifecycle_through_api(tmp_path):
    ctx = make_ctx(tmp_path)
    with make_client(ctx) as c:
        pid = c.post("/api/v1/projects", json={"title": "T"}).json()["id"]
        jid = c.post(f"/api/v1/projects/{pid}/artifacts", json=_body()).json()["job_id"]
        for _ in range(300):
            job = c.get(f"/api/v1/jobs/{jid}").json()
            if job["status"] == "succeeded":
                break
            time.sleep(0.05)
        assert job["status"] == "succeeded" and job["progress"] == 100
        assert c.post(f"/api/v1/jobs/{jid}:cancel").status_code == 409
        assert c.post(f"/api/v1/jobs/{jid}/retry").json() == {
            "detail": "only failed jobs can be retried"
        }
        assert c.get("/api/v1/jobs?status=nope").status_code == 422
        assert c.get("/api/v1/jobs/missing").status_code == 404
    ctx.close()
