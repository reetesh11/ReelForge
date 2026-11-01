"""AC-15 and the HTTP/WebSocket contract: projects, stages, jobs, artifacts, events."""

from __future__ import annotations

import time

from rf_helpers import (
    CountingAdapter,
    WsCollector,
    artifacts_of,
    create_project,
    make_client,
    make_ctx,
    make_settings,
    submit,
    wait_job,
)

PROJECT_KEYS = {
    "id",
    "slug",
    "title",
    "data_dir",
    "stage",
    "stages_approved",
    "brand_kit_id",
    "created_at",
    "updated_at",
}
JOB_KEYS = {
    "id",
    "project_id",
    "type",
    "status",
    "priority",
    "heavy",
    "mem_need_gb",
    "attempts",
    "progress",
    "message",
    "error",
    "pid",
    "exit_code",
    "peak_rss_mb",
    "command",
    "payload",
    "created_at",
    "started_at",
    "finished_at",
}
UNKNOWN = "01ARZ3NDEKTSV4RRFFQ69G5FAV"


def _ctx(tmp_path):
    return make_ctx(make_settings(tmp_path))


def test_project_crud(tmp_path):
    ctx = _ctx(tmp_path)
    with make_client(ctx, start_worker=False) as client:
        r = client.post("/api/v1/projects", json={"title": "My First Reel"})
        assert r.status_code == 201
        p = r.json()
        assert set(p) == PROJECT_KEYS
        assert (
            p["title"] == "My First Reel"
            and p["stage"] == "DRAFT"
            and p["stages_approved"] == 0
        )
        assert p["brand_kit_id"] is None and "my-first-reel" in p["slug"]
        root = ctx.settings.data_root / p["data_dir"]
        for sub in ("cast", "voices", "frames", "shots", "assembly", "uploads", "logs"):
            assert (root / sub).is_dir()
        assert client.get(f"/api/v1/projects/{p['id']}").json() == p

        time.sleep(1.1)
        u = client.patch(f"/api/v1/projects/{p['id']}", json={"title": "Renamed"})
        assert u.status_code == 200 and u.json()["title"] == "Renamed"
        assert u.json()["updated_at"] > p["updated_at"]

        assert client.delete(f"/api/v1/projects/{p['id']}").status_code == 204
        g = client.get(f"/api/v1/projects/{p['id']}")
        assert g.status_code == 404 and g.json() == {"detail": "project not found"}
    ctx.close()


def test_project_validation_list_order_and_duplicates(tmp_path):
    ctx = _ctx(tmp_path)
    with make_client(ctx, start_worker=False) as client:
        for bad in ({}, {"title": ""}, {"title": "x" * 201}, {"title": 5}):
            assert client.post("/api/v1/projects", json=bad).status_code == 422
        a = create_project(client, "Same")
        time.sleep(1.1)
        b = create_project(client, "Same")
        assert a["id"] != b["id"]
        assert [p["id"] for p in client.get("/api/v1/projects").json()] == [
            b["id"],
            a["id"],
        ]
        time.sleep(1.1)
        client.patch(f"/api/v1/projects/{a['id']}", json={"title": "Touched"})
        assert client.get("/api/v1/projects").json()[0]["id"] == a["id"]
        assert (
            client.patch(f"/api/v1/projects/{UNKNOWN}", json={"title": "x"}).status_code
            == 404
        )
        assert (
            client.patch(
                f"/api/v1/projects/{a['id']}", json={"stage": "NOPE"}
            ).status_code
            == 422
        )
        assert client.delete(f"/api/v1/projects/{UNKNOWN}").status_code == 404
    ctx.close()


def test_stages_endpoint_and_locking(tmp_path):
    ctx = _ctx(tmp_path)
    with make_client(ctx, start_worker=False) as client:
        p = create_project(client)
        stages = client.get(f"/api/v1/projects/{p['id']}/stages").json()["stages"]
        assert [(s["key"], s["label"]) for s in stages] == [
            ("story", "Story"),
            ("cast", "Cast"),
            ("voices", "Voices"),
            ("frames", "Key frames"),
            ("shots", "Shots"),
            ("assembly", "Assembly"),
        ]
        assert all(
            s["state"] == "not_started" and s["progress"] is None for s in stages
        )
        assert [s["locked"] for s in stages] == [False, True, True, True, True, True]

        r = client.patch(f"/api/v1/projects/{p['id']}", json={"stage": "CAST_APPROVED"})
        assert r.json()["stages_approved"] == 2
        stages = client.get(f"/api/v1/projects/{p['id']}/stages").json()["stages"]
        assert [s["state"] for s in stages][:3] == [
            "approved",
            "approved",
            "not_started",
        ]
        assert [s["locked"] for s in stages] == [False, False, False, True, True, True]
        assert client.get(f"/api/v1/projects/{UNKNOWN}/stages").status_code == 404
    ctx.close()


def test_stage_reflects_running_and_queued_jobs(tmp_path):
    ctx = _ctx(tmp_path)
    with make_client(ctx) as client:
        p = create_project(client)
        client.patch(f"/api/v1/projects/{p['id']}", json={"stage": "CAST_APPROVED"})
        j = submit(
            client,
            p["id"],
            stage="voices",
            media="audio",
            kind="voice_take",
            params={"mock": {"sleep_s": 3, "steps": 10}},
        )["job_id"]
        wait_job(ctx, j, {"running"})
        deadline = time.monotonic() + 15
        voices = None
        while time.monotonic() < deadline:
            voices = client.get(f"/api/v1/projects/{p['id']}/stages").json()["stages"][
                2
            ]
            if voices["state"] == "rendering":
                break
            time.sleep(0.1)
        assert voices["state"] == "rendering" and isinstance(voices["progress"], int)
        ctx.queue.cancel(j)
    ctx.close()


def test_artifacts_endpoint(tmp_path):
    ctx = _ctx(tmp_path)
    with make_client(ctx) as client:
        p = create_project(client)
        first = submit(client, p["id"])
        assert (
            first["cache_hit"] is False
            and first["job_id"]
            and first["artifact_id"] is None
        )
        wait_job(ctx, first["job_id"], {"succeeded"})
        second = submit(client, p["id"])
        assert (
            second["cache_hit"] is True
            and second["job_id"] is None
            and second["artifact_id"]
        )
        assert second["artifact_id"] == artifacts_of(ctx, p["id"])[0].id
        r = client.post(
            f"/api/v1/projects/{UNKNOWN}/artifacts",
            json={
                "owner_type": "c",
                "owner_id": "o",
                "kind": "candidate",
                "media": "image",
                "prompt": "p",
                "seed": 1,
            },
        )
        assert r.status_code == 404
    ctx.close()


def test_jobs_list_get_filters_and_json_shape(tmp_path):
    ctx = _ctx(tmp_path)
    with make_client(ctx) as client:
        p = create_project(client)
        job_id = submit(client, p["id"])["job_id"]
        wait_job(ctx, job_id, {"succeeded"})
        q = create_project(client, "Other")
        listed = client.get("/api/v1/jobs").json()
        assert [j["id"] for j in listed] == [job_id]
        assert set(listed[0]) == JOB_KEYS
        assert listed[0]["status"] == "succeeded" and listed[0]["progress"] == 100
        assert (
            client.get(f"/api/v1/jobs?status=succeeded&project={p['id']}").json()[0][
                "id"
            ]
            == job_id
        )
        assert client.get("/api/v1/jobs?status=failed").json() == []
        assert client.get(f"/api/v1/jobs?project={q['id']}").json() == []
        assert client.get("/api/v1/jobs?status=bogus").status_code == 422
        assert client.get(f"/api/v1/jobs/{job_id}").json()["id"] == job_id
        g = client.get(f"/api/v1/jobs/{UNKNOWN}")
        assert g.status_code == 404 and g.json() == {"detail": "job not found"}
    ctx.close()


def test_cancel_running_job_via_api(tmp_path):
    ctx = _ctx(tmp_path)
    with make_client(ctx) as client:
        p = create_project(client)
        job_id = submit(client, p["id"], params={"mock": {"sleep_s": 60}})["job_id"]
        wait_job(ctx, job_id, {"running"})
        r = client.post(f"/api/v1/jobs/{job_id}/cancel")
        assert r.status_code == 200
        assert (
            wait_job(
                ctx, job_id, {"cancelled", "succeeded", "failed"}, timeout=20
            ).status
            == "cancelled"
        )
        again = client.post(f"/api/v1/jobs/{job_id}/cancel")
        assert again.status_code == 409 and again.json() == {
            "detail": "job already finished"
        }
        assert client.post(f"/api/v1/jobs/{UNKNOWN}/cancel").status_code == 404
    ctx.close()


def test_retry_failed_job_via_api_runs_to_success(tmp_path):
    from reelforge.artifacts.service import ArtifactRequest
    from reelforge.db.models import Job
    from sqlalchemy import update

    ctx = _ctx(tmp_path)
    with make_client(ctx, start_worker=False) as c0:
        p = create_project(c0)
    req = ArtifactRequest(
        project_id=p["id"],
        owner_type="character",
        owner_id="o",
        kind="candidate",
        media="image",
        prompt="p",
        seed=3,
    )
    job = ctx.queue.enqueue(
        type="artifact.generate", project_id=p["id"], payload=req.model_dump()
    )
    with ctx.session_factory() as s, s.begin():
        s.execute(
            update(Job)
            .where(Job.id == job.id)
            .values(status="failed", error="boom", attempts=2)
        )
    with make_client(ctx) as client:
        r = client.post(f"/api/v1/jobs/{job.id}/retry")
        assert r.status_code == 200 and r.json()["status"] == "queued"
        assert wait_job(ctx, job.id, {"succeeded", "failed"}).status == "succeeded"
        bad = client.post(f"/api/v1/jobs/{job.id}/retry")
        assert bad.status_code == 409 and bad.json() == {
            "detail": "only failed jobs can be retried"
        }
    assert len(artifacts_of(ctx, p["id"])) == 1
    ctx.close()


def test_websocket_streams_job_artifact_and_stage_events(tmp_path):
    settings = make_settings(tmp_path)
    ctx = make_ctx(settings, adapter=CountingAdapter(settings))
    with make_client(ctx) as client:
        ws = WsCollector(client)
        p = create_project(client)
        job_id = submit(client, p["id"], params={"mock": {"sleep_s": 1.0, "steps": 5}})[
            "job_id"
        ]
        done = ws.wait_for(
            lambda m: m["type"] == "job.updated" and m["data"]["status"] == "succeeded"
        )
        assert set(done["data"]) == {
            "job_id",
            "project_id",
            "status",
            "progress",
            "eta_s",
            "message",
            "error",
        }
        assert done["data"]["job_id"] == job_id and done["data"]["progress"] == 100
        assert done["data"]["project_id"] == p["id"] and done["data"]["eta_s"] is None
        progress = [
            m["data"]["progress"] for m in ws.seen if m["type"] == "job.updated"
        ]
        assert all(isinstance(x, int) and 0 <= x <= 100 for x in progress)
        assert progress == sorted(progress)
        art = ws.wait_for(lambda m: m["type"] == "artifact.created")
        assert set(art["data"]) == {
            "project_id",
            "owner_type",
            "owner_id",
            "kind",
            "artifact_id",
            "take_no",
        }
        assert (
            art["data"]["artifact_id"] == artifacts_of(ctx, p["id"])[0].id
            and art["data"]["take_no"] == 1
        )

        client.patch(f"/api/v1/projects/{p['id']}", json={"stage": "STORY_APPROVED"})
        st = ws.wait_for(lambda m: m["type"] == "stage.changed")
        assert st["data"] == {"project_id": p["id"], "stage": "STORY_APPROVED"}
        ws.close()
        # a disconnected client does not affect jobs
        j2 = submit(client, p["id"], seed=9)["job_id"]
        assert wait_job(ctx, j2, {"succeeded", "failed"}).status == "succeeded"
    ctx.close()


def test_health_changed_event_only_for_changed_checks(tmp_path):
    from rf_helpers import passing_report

    state: dict[str, str] = {}
    ctx = make_ctx(make_settings(tmp_path), doctor=lambda: passing_report(dict(state)))
    with make_client(ctx) as client:
        ws = WsCollector(client)
        ctx.health.poll_once()
        state["ltx"] = "blocking"
        changed = ctx.health.poll_once()
        assert [c.name for c in changed] == ["ltx"]
        ev = ws.wait_for(
            lambda m: m["type"] == "health.changed" and m["data"]["service"] == "ltx"
        )
        assert ev["data"] == {"service": "ltx", "status": "fail"}
        assert ctx.health.poll_once() == []
        ws.close()
    ctx.close()


def test_openapi_export_is_sorted_and_matches_committed_file(tmp_path):
    import json

    from reelforge.api.openapi_export import export
    from rf_helpers import REPO_ROOT

    out = tmp_path / "openapi.json"
    export(out)
    text = out.read_text()
    assert text.endswith("\n")
    doc = json.loads(text)
    assert "/health" in doc["paths"] and "/api/v1/projects" in doc["paths"]
    assert text == json.dumps(doc, indent=2, sort_keys=True) + "\n"
    assert (REPO_ROOT / "web" / "openapi.json").read_text() == text
