"""AC-1 (reuse copies master, look, seed, voice ref), AC-2 (variant, library untouched)."""

from __future__ import annotations

import hashlib

from m3_helpers import approved_project, cast_item, cast_url, gen_and_approve, new_world


def _library_from_project_a(client, ctx):
    """Approve a cast in project A, then give the tomato a voice reference through the library."""
    a = approved_project(client, "Project A")
    gen_and_approve(client, ctx, a, "tomato", seed=60)
    gen_and_approve(client, ctx, a, "potato", seed=70)
    item = cast_item(client, a, "tomato")
    # a second library record carrying a voice reference and the same master
    r = client.post(
        "/api/v1/library/characters",
        json={
            "name": "Tamatar voiced",
            "aliases": ["Tom"],
            "look_text": item["bible_line"],
            "seed": item["seed"],
            "voice_reference": "voice_tomato_01",
            "master_artifact_id": item["master_artifact_id"],
            "tags": ["fruit"],
        },
    )
    assert r.status_code == 201, r.text
    return a, item, r.json()


def test_second_project_gets_identical_master_look_seed_voice(tmp_path):
    ctx, client, adapter = new_world(tmp_path)
    with client:
        a, a_item, voiced = _library_from_project_a(client, ctx)
        assert voiced["voice_reference"] == "voice_tomato_01" and voiced["tags"] == ["fruit"]
        assert voiced["master_sha256"] == a_item["master_sha256"]
        assert len(client.get("/api/v1/library/characters").json()) == 3

        b = approved_project(client, "Project B")
        calls = len(adapter.calls)
        r = client.post(cast_url(b, "tomato", "use-library"), json={"character_id": voiced["id"]})
        assert r.status_code == 200, r.text
        item = r.json()["character"]
        lib = client.get(f"/api/v1/library/characters/{voiced['id']}").json()
        assert item["master_sha256"] == lib["master_sha256"]
        master = client.get(lib["master_image_url"]).content
        assert hashlib.sha256(master).hexdigest() == item["master_sha256"]
        assert item["bible_line"] == lib["look_text"]
        assert item["seed"] == lib["seed"]
        assert item["voice_reference"] == "voice_tomato_01"
        assert item["approved"] is True and item["library_character_id"] == voiced["id"]
        assert "variant_of_library_id" not in item
        assert len(adapter.calls) == calls  # reuse needs no generation
        from rf_helpers import artifacts_of

        assert len([x for x in artifacts_of(ctx, b) if x.kind == "cast_master"]) == 1

        r = client.post(cast_url(b, "tomato", "use-library"), json={"character_id": "missing"})
        assert r.status_code == 404
        assert r.json() == {"detail": "That library character no longer exists."}


def test_use_library_requires_master_image(tmp_path):
    ctx, client, _ = new_world(tmp_path)
    with client:
        r = client.post("/api/v1/library/characters", json={"name": "NoImg", "look_text": "x"})
        assert r.status_code == 201 and "master_image_url" not in r.json()
        b = approved_project(client)
        r2 = client.post(cast_url(b, "tomato", "use-library"), json={"character_id": r.json()["id"]})
        assert r2.status_code == 409


def test_editing_look_creates_variant_and_library_original_is_unchanged(tmp_path):
    ctx, client, adapter = new_world(tmp_path)
    with client:
        a, _, voiced = _library_from_project_a(client, ctx)
        cid = voiced["id"]
        before = client.get(f"/api/v1/library/characters/{cid}").json()
        before_list = client.get("/api/v1/library/characters").json()

        b = approved_project(client, "Project B")
        assert client.post(
            cast_url(b, "tomato", "use-library"), json={"character_id": cid}
        ).status_code == 200

        from m3_helpers import generate

        _, job = generate(
            client, ctx, b, "tomato", look_text=before["look_text"] + ", now wearing a blue outfit"
        )
        assert job.status == "succeeded", job.error
        item = cast_item(client, b, "tomato")
        assert item["variant_of_library_id"] == cid
        vid = item["library_character_id"]
        assert vid and vid != cid

        variant = client.get(f"/api/v1/library/characters/{vid}").json()
        assert variant["parent_character_id"] == cid
        assert variant["name"] == "Tamatar voiced (variant)"

        after = client.get(f"/api/v1/library/characters/{cid}").json()
        assert after == before
        assert "parent_character_id" not in after
        ids = [c["id"] for c in client.get("/api/v1/library/characters").json()]
        assert set(ids) == {c["id"] for c in before_list} | {vid}

        # approving a new candidate for the variant never touches the original either
        cand = cast_item(client, b, "tomato")["candidates"][0]
        r = client.post(cast_url(b, "tomato", "approve"), json={"candidate_id": cand["id"]})
        assert r.status_code == 200, r.text
        assert client.get(f"/api/v1/library/characters/{cid}").json() == before


def test_patch_only_name_aliases_tags(tmp_path):
    ctx, client, _ = new_world(tmp_path)
    with client:
        r = client.post(
            "/api/v1/library/characters", json={"name": "A", "look_text": "look one", "seed": 5}
        )
        cid = r.json()["id"]
        for key, val in [("look_text", "x"), ("seed", 9), ("model", "m"), ("master_artifact_id", "z")]:
            bad = client.patch(f"/api/v1/library/characters/{cid}", json={key: val})
            assert bad.status_code == 400
            assert bad.json() == {"detail": "Only name, aliases and tags can be changed."}
        ok = client.patch(
            f"/api/v1/library/characters/{cid}", json={"name": "B", "aliases": ["bee"], "tags": ["t"]}
        )
        assert ok.status_code == 200
        assert (ok.json()["name"], ok.json()["aliases"], ok.json()["tags"]) == ("B", ["bee"], ["t"])
        got = client.get(f"/api/v1/library/characters/{cid}").json()
        assert got["look_text"] == "look one" and got["seed"] == 5
        assert client.patch("/api/v1/library/characters/nope", json={"name": "x"}).status_code == 404
        assert client.get("/api/v1/library/characters/nope").status_code == 404
        assert client.post(
            "/api/v1/library/characters",
            json={"name": "C", "look_text": "l", "master_artifact_id": "missing"},
        ).status_code == 404
