from _helpers import make_client, make_ctx

from reelforge.api.stages import derive_stages, stages_approved


def test_crud_and_stage_patch(tmp_path):
    ctx = make_ctx(tmp_path)
    with make_client(ctx, start_worker=False) as c:
        p = c.post("/api/v1/projects", json={"title": "Hello World!"}).json()
        assert "hello-world" in p["slug"] and p["stage"] == "DRAFT"
        assert c.post("/api/v1/projects", json={"title": ""}).status_code == 422
        q = c.patch(f"/api/v1/projects/{p['id']}", json={"stage": "VOICES_APPROVED"}).json()
        assert q["stages_approved"] == 3
        stages = c.get(f"/api/v1/projects/{p['id']}/stages").json()["stages"]
        assert [s["state"] for s in stages[:4]] == ["approved"] * 3 + ["not_started"]
        assert c.delete(f"/api/v1/projects/{p['id']}").status_code == 204
        assert c.get(f"/api/v1/projects/{p['id']}").status_code == 404
    ctx.close()


def test_stage_gate_helpers():
    assert stages_approved("EXPORTED") == 6 and stages_approved("DRAFT") == 0
    stages = derive_stages("DRAFT", [])
    assert [s.locked for s in stages] == [False] + [True] * 5
