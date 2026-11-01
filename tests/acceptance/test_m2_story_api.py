"""AC-1, AC-2, AC-3, AC-5, AC-6, AC-10, AC-11 over HTTP on the mock LLM."""

from __future__ import annotations

import time

from rf_helpers import create_project, make_client, store_bytes
from story_helpers import STORY_YAML, import_, new_ctx, put, structure, versions


def _setup(tmp_path, llm=None):
    ctx = new_ctx(tmp_path, llm=llm)
    return ctx, make_client(ctx)


def test_structure_on_mock_saves_valid_version_and_put_moves_current(tmp_path):
    from reelforge.story.yamlio import parse_story

    ctx, client = _setup(tmp_path)
    with client:
        pid = create_project(client)["id"]
        job = structure(client, ctx, pid)
        assert job.status == "succeeded", job.error
        res = client.get(f"/api/v1/jobs/{job.id}").json()["result"]
        assert res["questions"] == [] and res["draft_yaml"] is None
        assert res["version"]["is_current"] is True
        cur = client.get(f"/api/v1/projects/{pid}/story").json()
        story = parse_story(cur["yaml_text"])
        assert sorted(story.characters) == ["potato", "tomato"] and len(story.scenes) == 5
        assert len(versions(client, pid)) == 1

        r = put(client, pid, cur["yaml_text"])
        assert r.status_code == 200 and r.json()["is_current"] is True
        vs = versions(client, pid)
        assert len(vs) == 2
        assert [v["is_current"] for v in vs] == [True, False]
        assert vs[0]["version"] > vs[1]["version"]
        assert vs[0]["id"] == r.json()["id"]


def test_structure_empty_storyline_422(tmp_path):
    ctx, client = _setup(tmp_path)
    with client:
        pid = create_project(client)["id"]
        r = client.post(f"/api/v1/projects/{pid}/story:structure", json={"storyline": "  \n"})
        assert r.status_code == 422 and r.json() == {"detail": "storyline is required"}


def test_put_and_import_reject_bad_story_naming_fields(tmp_path):
    ctx, client = _setup(tmp_path)
    with client:
        pid = create_project(client)["id"]
        bad = STORY_YAML.replace("fps: 24", 'fps: "abc"') + "foo: 1\n"
        for fn in (put, import_):
            r = fn(client, pid, bad)
            assert r.status_code == 422, r.text
            body = r.json()
            assert body["detail"] == "story.yaml is invalid"
            got = {(e["path"], e["message"]) for e in body["errors"]}
            assert ("foo", "unknown field") in got and ("fps", "must be an integer") in got
        assert versions(client, pid) == []
        assert client.get(f"/api/v1/projects/{pid}/story").status_code == 404


def test_put_empty_malformed_and_oversize(tmp_path):
    ctx, client = _setup(tmp_path)
    with client:
        pid = create_project(client)["id"]
        r = put(client, pid, "")
        assert r.status_code == 422 and r.json()["errors"][0]["message"] == "story.yaml is empty"
        r = put(client, pid, "title: [oops\n")
        assert r.status_code == 422 and r.json()["errors"][0]["line"] is not None
        r = put(client, pid, "#" * (1_048_576 + 1))
        assert r.status_code == 413 and r.json() == {"detail": "story.yaml is larger than 1 MB"}
        assert versions(client, pid) == []
        r = put(client, "01ARZ3NDEKTSV4RRFFQ69G5FAV", STORY_YAML)
        assert r.status_code == 404 and r.json() == {"detail": "project not found"}


def test_put_roundtrip_stores_text_exactly(tmp_path):
    ctx, client = _setup(tmp_path)
    with client:
        p = create_project(client)
        r = put(client, p["id"], STORY_YAML)
        assert r.status_code == 200
        assert client.get(f"/api/v1/projects/{p['id']}/story").json()["yaml_text"] == STORY_YAML
        assert (ctx.settings.data_root / p["data_dir"] / "story.yaml").read_text() == STORY_YAML


def test_import_and_export_byte_identical_with_zero_llm_calls(tmp_path):
    from reelforge.adapters.mock_llm import MockLlm

    llm = MockLlm()
    ctx, client = _setup(tmp_path, llm)
    with client:
        pid = create_project(client)["id"]
        r = import_(client, pid, STORY_YAML)
        assert r.status_code == 201 and r.json()["is_current"] is True
        assert llm.calls == []
        e = client.get(f"/api/v1/projects/{pid}/story/export")
        assert e.status_code == 200
        assert e.headers["content-type"].startswith("application/yaml")
        assert e.content == STORY_YAML.encode("utf-8")
        assert client.get(f"/api/v1/projects/{pid}/story/versions/1").json()["yaml_text"] == STORY_YAML
        assert client.get(f"/api/v1/projects/{pid}/story/versions/9").status_code == 404


def test_export_404_without_story(tmp_path):
    ctx, client = _setup(tmp_path)
    with client:
        pid = create_project(client)["id"]
        assert client.get(f"/api/v1/projects/{pid}/story/export").status_code == 404


def test_unsafe_tag_rejected_on_put_and_import(tmp_path):
    ctx, client = _setup(tmp_path)
    with client:
        pid = create_project(client)["id"]
        evil = "version: 1\ntitle: !!python/object/apply:os.system [echo hi]\n" + STORY_YAML.split("\n", 3)[3]
        for fn in (put, import_):
            r = fn(client, pid, evil)
            assert r.status_code == 422
            assert "unsafe or unsupported YAML tag" in [e["message"] for e in r.json()["errors"]]
        assert versions(client, pid) == []


def test_schema_endpoint_served(tmp_path):
    from reelforge.story.schema import story_json_schema

    ctx, client = _setup(tmp_path)
    with client:
        r = client.get("/api/v1/story/schema")
        assert r.status_code == 200 and r.json() == story_json_schema()


def test_approve_flow_and_errors(tmp_path):
    ctx, client = _setup(tmp_path)
    with client:
        pid = create_project(client)["id"]
        r = client.post(f"/api/v1/projects/{pid}/story:approve")
        assert r.status_code == 409 and r.json() == {"detail": "There is no story to approve yet."}
        put(client, pid, STORY_YAML)
        r = client.post(f"/api/v1/projects/{pid}/story:approve")
        assert r.status_code == 200 and r.json()["stage"] == "STORY_APPROVED"
        cur = client.get(f"/api/v1/projects/{pid}/story").json()
        assert cur["approved_at"] is not None
        assert client.post(f"/api/v1/projects/{pid}/story:approve").status_code == 200


def test_edit_after_approve_drafts_and_marks_only_that_scene(tmp_path):
    ctx, client = _setup(tmp_path)
    with client:
        pid = create_project(client)["id"]
        put(client, pid, STORY_YAML)
        client.post(f"/api/v1/projects/{pid}/story:approve")
        for owner_type, owner, kind in [
            ("scene", "s2", "voice_take"),
            ("scene", "s2", "shot"),
            ("scene", "s3", "voice_take"),
            ("scene", "s3", "shot"),
            ("character", "tomato", "candidate"),
            ("character", "potato", "candidate"),
        ]:
            store_bytes(ctx, pid, f"{owner}{kind}".encode(), owner_type=owner_type, owner_id=owner, kind=kind, subdir="x")
        time.sleep(1.1)
        edited = STORY_YAML.replace("Arre Aloo, itni der kyun?", "Kahan the tum?")
        r = put(client, pid, edited)
        assert r.status_code == 200
        assert r.json()["affected"] == [
            {"owner_type": "scene", "owner_id": "s2", "kinds": ["voice_take", "shot"]}
        ]
        assert client.get(f"/api/v1/projects/{pid}").json()["stage"] == "DRAFT"
        items = client.get(f"/api/v1/projects/{pid}/stale").json()["items"]
        assert {(i["owner_type"], i["owner_id"], i["kind"]) for i in items} == {
            ("scene", "s2", "voice_take"),
            ("scene", "s2", "shot"),
        }
        # versions: approved one remains, new one is current and unapproved
        vs = versions(client, pid)
        assert [v["is_current"] for v in vs] == [True, False]
        assert vs[0]["approved_at"] is None and vs[1]["approved_at"] is not None


def test_other_scene_field_and_character_look_staleness(tmp_path):
    ctx, client = _setup(tmp_path)
    with client:
        pid = create_project(client)["id"]
        put(client, pid, STORY_YAML)
        client.post(f"/api/v1/projects/{pid}/story:approve")
        first = STORY_YAML.replace("Aloo bursts in through", "Aloo runs in through")
        r = put(client, pid, first)
        assert r.json()["affected"] == [{"owner_type": "scene", "owner_id": "s1", "kinds": ["*"]}]
        client.post(f"/api/v1/projects/{pid}/story:approve")
        r = put(client, pid, first.replace("pink turban", "green turban"))
        aff = {(a["owner_type"], a["owner_id"]): a["kinds"] for a in r.json()["affected"]}
        assert aff == {("character", "potato"): ["*"]}


def test_semantically_identical_put_creates_version_but_nothing_stale(tmp_path):
    ctx, client = _setup(tmp_path)
    with client:
        pid = create_project(client)["id"]
        put(client, pid, STORY_YAML)
        client.post(f"/api/v1/projects/{pid}/story:approve")
        r = put(client, pid, STORY_YAML.replace("# Tomato tale", "# Renamed comment"))
        assert r.status_code == 200 and r.json()["affected"] == []
        assert client.get(f"/api/v1/projects/{pid}").json()["stage"] == "STORY_APPROVED"
        assert len(versions(client, pid)) == 2
        assert client.get(f"/api/v1/projects/{pid}/stale").json() == {"items": []}


def test_approve_blocked_while_structure_job_runs(tmp_path):
    ctx2 = new_ctx(tmp_path)
    with make_client(ctx2, start_worker=False) as c2:
        pid2 = create_project(c2)["id"]
        put(c2, pid2, STORY_YAML)
        r = c2.post(f"/api/v1/projects/{pid2}/story:structure", json={"storyline": "x"})
        assert r.status_code == 202
        j = r.json()
        assert j["type"] == "story.structure" and j["payload"]["stage"] == "story" and j["heavy"] is False
        r = c2.post(f"/api/v1/projects/{pid2}/story:approve")
        assert r.status_code == 409 and r.json() == {"detail": "A structuring job is running."}
