"""AC-10 (stage), AC-5 (upload), AC-7 (licence), plus approval side effects (R9)."""

from __future__ import annotations

import hashlib
import re
import subprocess

from m3_helpers import (
    approve,
    approved_project,
    cast_item,
    cast_url,
    generate,
    models_with_license,
    new_world,
    png_bytes,
)
from rf_helpers import artifacts_of, sidecar_of


def _ready(client, ctx, pid, key, **body):
    _, job = generate(client, ctx, pid, key, **body)
    assert job.status == "succeeded", job.error
    return cast_item(client, pid, key)["candidates"]


def test_stage_becomes_cast_approved_only_after_last_character(tmp_path):
    ctx, client, _ = new_world(tmp_path)
    with client:
        pid = approved_project(client)
        t = _ready(client, ctx, pid, "tomato", seed=1)
        p = _ready(client, ctx, pid, "potato", seed=2)

        r = approve(client, pid, "tomato", t[2]["id"])
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["project_stage"] == "STORY_APPROVED"
        assert (body["approved_count"], body["total"]) == (1, 2)
        assert body["character"]["approved"] is True and body["character"]["state"] == "approved"
        assert client.get(f"/api/v1/projects/{pid}").json()["stage"] == "STORY_APPROVED"

        # idempotent
        arts = len(artifacts_of(ctx, pid))
        again = approve(client, pid, "tomato", t[2]["id"])
        assert again.status_code == 200 and again.json()["approved_count"] == 1
        assert len(artifacts_of(ctx, pid)) == arts
        assert len(client.get("/api/v1/library/characters").json()) == 1

        r = approve(client, pid, "potato", p[0]["id"])
        assert r.json()["project_stage"] == "CAST_APPROVED"
        assert (r.json()["approved_count"], r.json()["total"]) == (2, 2)
        assert client.get(f"/api/v1/projects/{pid}").json()["stage"] == "CAST_APPROVED"

        r = client.post(cast_url(pid, "potato", "reopen"))
        assert r.status_code == 200 and r.json()["project_stage"] == "STORY_APPROVED"
        assert client.get(f"/api/v1/projects/{pid}").json()["stage"] == "STORY_APPROVED"


def test_approve_unknown_candidate_404(tmp_path):
    ctx, client, _ = new_world(tmp_path)
    with client:
        pid = approved_project(client)
        t = _ready(client, ctx, pid, "tomato", seed=1)
        p = _ready(client, ctx, pid, "potato", seed=9)
        for cid in ("nope", p[0]["id"]):
            r = approve(client, pid, "tomato", cid)
            assert r.status_code == 404 and r.json() == {"detail": "candidate not found"}
        assert cast_item(client, pid, "tomato")["approved"] is False
        assert t


def test_approval_creates_master_library_record_and_mirror(tmp_path):
    ctx, client, _ = new_world(tmp_path)
    with client:
        pid = approved_project(client)
        t = _ready(client, ctx, pid, "tomato", seed=40)
        chosen = t[1]
        r = approve(client, pid, "tomato", chosen["id"])
        assert r.status_code == 200, r.text
        item = r.json()["character"]
        assert item["seed"] == 41 and item["voice_reference"] == ""
        assert re.fullmatch(r"[0-9a-f]{64}", item["master_sha256"])
        masters = [a for a in artifacts_of(ctx, pid) if a.kind == "cast_master"]
        assert len(masters) == 1 and masters[0].id == item["master_artifact_id"]

        cid = item["library_character_id"]
        lib = client.get(f"/api/v1/library/characters/{cid}")
        assert lib.status_code == 200
        rec = lib.json()
        assert rec["name"] == "Tamatar" and rec["look_text"] == item["bible_line"]
        assert rec["seed"] == 41 and rec["tags"] == [] and rec["created_at"]
        assert rec["model"] == "image" and rec["model_id"] == chosen["model"]
        assert rec["master_sha256"] == item["master_sha256"]
        img = client.get(rec["master_image_url"])
        assert img.status_code == 200
        assert hashlib.sha256(img.content).hexdigest() == item["master_sha256"]

        mirrors = [
            p for p in ctx.settings.data_root.rglob("character.json")
            if p.parent.name == cid and "characters" in p.parts and "library" in p.parts
        ]
        assert len(mirrors) == 1
        import json

        assert json.loads(mirrors[0].read_text()) == rec


def test_reapproving_same_character_creates_no_duplicate_library_record(tmp_path):
    """AC-15: approving a character already in the library from the same project adds no duplicate."""
    ctx, client, _ = new_world(tmp_path)
    with client:
        pid = approved_project(client)
        t = _ready(client, ctx, pid, "tomato", seed=50)
        r1 = approve(client, pid, "tomato", t[0]["id"])
        assert r1.status_code == 200, r1.text
        cid = r1.json()["character"]["library_character_id"]
        r2 = approve(client, pid, "tomato", t[1]["id"])
        assert r2.status_code == 200, r2.text
        assert r2.json()["character"]["library_character_id"] == cid
        items = client.get("/api/v1/library/characters").json()
        assert len([c for c in items if c["name"] == "Tamatar"]) == 1
        mirrors = [p for p in ctx.settings.data_root.rglob("character.json") if "library" in p.parts]
        assert len(mirrors) == 1


def _upload(client, pid, key, data: bytes, name="evil name.png", ctype="image/png"):
    return client.post(
        cast_url(pid, key, "upload"), files={"file": (name, data, ctype)}
    )


def _jpeg(tmp_path) -> bytes:
    out = tmp_path / "x.jpg"
    subprocess.run(
        ["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi", "-i", "color=c=red:s=32x64",
         "-frames:v", "1", str(out)],
        check=True,
    )
    return out.read_bytes()


def test_upload_png_and_jpeg_replace_candidates_with_generated_name(tmp_path):
    ctx, client, _ = new_world(tmp_path)
    with client:
        pid = approved_project(client)
        _ready(client, ctx, pid, "tomato", seed=1)
        assert len(cast_item(client, pid, "tomato")["candidates"]) == 4

        r = _upload(client, pid, "tomato", png_bytes(32, 64), name="my evil name.png")
        assert r.status_code == 201, r.text
        cands = r.json()["candidates"]
        assert len(cands) == 1 and cands[0]["kind"] == "upload"
        up = [a for a in artifacts_of(ctx, pid) if a.kind == "cast_upload"]
        assert len(up) == 1 and up[0].id == cands[0]["id"]
        path = ctx.store.absolute_path(up[0])
        assert path.read_bytes() == png_bytes(32, 64)
        assert "uploads" in path.parts and re.fullmatch(r"take_\d{3}\.png", path.name)
        assert "evil" not in str(path)
        assert [c["id"] for c in cast_item(client, pid, "tomato")["candidates"]] == [cands[0]["id"]]

        r = _upload(client, pid, "tomato", _jpeg(tmp_path), name="photo.jpeg", ctype="image/jpeg")
        assert r.status_code == 201, r.text
        assert len(r.json()["candidates"]) == 1
        jp = [a for a in artifacts_of(ctx, pid) if a.kind == "cast_upload"][-1]
        assert re.fullmatch(r"take_\d{3}\.jpg", ctx.store.absolute_path(jp).name)


def test_upload_rejects_wrong_content_and_oversize_without_side_effects(tmp_path):
    ctx, client, _ = new_world(tmp_path, max_upload_mb=1)
    with client:
        pid = approved_project(client)
        before = len(artifacts_of(ctx, pid))
        for data in (b"just some text, not an image", b"", b"\x89PNG\r\n\x1a\n" + b"junk"):
            r = _upload(client, pid, "tomato", data, name="fake.png", ctype="image/png")
            assert r.status_code == 415, r.text
            assert r.json() == {"detail": "That file isn't a PNG or JPEG image."}
        big = png_bytes(8, 16) + b"\x00" * (1024 * 1024 + 10)
        r = _upload(client, pid, "tomato", big)
        assert r.status_code == 413
        assert r.json() == {"detail": "That image is larger than 1 MB."}
        assert len(artifacts_of(ctx, pid)) == before
        assert cast_item(client, pid, "tomato")["candidates"] == []
        assert not [p for p in ctx.settings.data_root.rglob("*") if p.parent.name == "uploads" and p.is_file()]
        assert _upload(client, "01ARZ3NDEKTSV4RRFFQ69G5FAV", "tomato", png_bytes()).status_code == 404


NC = "FLUX.1 Kontext [dev] Non-Commercial License"


def test_licence_warning_everywhere_and_approval_still_succeeds(tmp_path):
    models = models_with_license(tmp_path / "models.toml", NC, "https://example.invalid/nc")
    ctx, client, _ = new_world(tmp_path, models_path=models)
    with client:
        pid = approved_project(client)
        expected = f"Image model licence: {NC} - not for commercial use. See https://example.invalid/nc."
        assert client.get("/health").json()["image_licence_warning"] == expected
        assert get_warning(client, pid) == expected

        cands = _ready(client, ctx, pid, "tomato", seed=3)
        assert all(c["license"] == NC and c["license_url"] == "https://example.invalid/nc" for c in cands)
        for c in cands:
            side = sidecar_of(ctx, next(a for a in artifacts_of(ctx, pid) if a.id == c["id"]))
            assert side["license"] == NC and side["license_url"] == "https://example.invalid/nc"

        r = approve(client, pid, "tomato", cands[0]["id"])
        assert r.status_code == 200, r.text
        master = next(a for a in artifacts_of(ctx, pid) if a.kind == "cast_master")
        assert sidecar_of(ctx, master)["license"] == NC


def get_warning(client, pid):
    return client.get(cast_url(pid)).json().get("licence_warning")


def test_licence_warning_text_rules():
    from reelforge.cast.licence import licence_warning
    from reelforge.models_registry import ModelEntry

    def entry(lic, url=""):
        return ModelEntry(key="image", id="img-1", revision="r", license=lic, license_url=url)

    assert licence_warning(entry("")) == (
        "Image model licence is not filled in. Check img-1 before commercial use."
    )
    assert licence_warning(entry("CC-BY-NC-4.0", "u")) == (
        "Image model licence: CC-BY-NC-4.0 - not for commercial use. See u."
    )
    for lic in ("Non-Commercial", "noncommercial use", "Non Commercial"):
        assert licence_warning(entry(lic, "u")) is not None
    assert licence_warning(entry("Apache-2.0", "u")) is None
    assert licence_warning(entry("mit")) is None


def test_permissive_licence_has_no_warning_in_cast(tmp_path):
    ctx, client, _ = new_world(tmp_path)
    with client:
        pid = approved_project(client)
        r = client.get(cast_url(pid))
        assert r.status_code == 200
        assert "licence_warning" not in r.json()
