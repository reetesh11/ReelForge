"""Library routes: round trip, restricted PATCH, mirror equality, master bytes."""

from __future__ import annotations

import json
import struct
import zlib

from _helpers import make_client, make_ctx, spec_for


def _png() -> bytes:
    def chunk(tag: bytes, data: bytes) -> bytes:
        body = tag + data
        return struct.pack(">I", len(data)) + body + struct.pack(">I", zlib.crc32(body))

    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0))
        + chunk(b"IDAT", zlib.compress(b"\x00\x01\x02\x03"))
        + chunk(b"IEND", b"")
    )


def _mirror(ctx, cid):
    path = ctx.settings.data_root / "library" / "characters" / cid / "character.json"
    return json.loads(path.read_text())


def test_create_get_list_round_trip(tmp_path):
    ctx = make_ctx(tmp_path)
    with make_client(ctx, start_worker=False) as client:
        r = client.post(
            "/api/v1/library/characters",
            json={"name": "A", "look_text": "look", "aliases": ["a"], "tags": ["t"], "seed": 3},
        )
        assert r.status_code == 201
        rec = r.json()
        assert client.get(f"/api/v1/library/characters/{rec['id']}").json() == rec
        assert client.get("/api/v1/library/characters").json() == [rec]
        assert rec["voice_reference"] == "" and "master_image_url" not in rec
        assert _mirror(ctx, rec["id"]) == rec
        assert client.get(f"/api/v1/library/characters/{rec['id']}/master").status_code == 404


def test_patch_rewrites_mirror_and_master_bytes_are_copied(tmp_path):
    ctx = make_ctx(tmp_path)
    with make_client(ctx, start_worker=False) as client:
        pid = client.post("/api/v1/projects", json={"title": "T"}).json()["id"]
        art = ctx.store.write(spec_for(pid), _png(), ext="png")
        rec = client.post(
            "/api/v1/library/characters",
            json={"name": "A", "look_text": "look", "master_artifact_id": art.id},
        ).json()
        got = client.get(rec["master_image_url"])
        assert got.status_code == 200 and got.content == _png()
        assert got.headers["content-type"] == "image/png"
        ok = client.patch(f"/api/v1/library/characters/{rec['id']}", json={"tags": ["x"]})
        assert ok.status_code == 200 and ok.json()["tags"] == ["x"]
        assert _mirror(ctx, rec["id"]) == ok.json()
        bad = client.patch(f"/api/v1/library/characters/{rec['id']}", json={"look_text": "no"})
        assert bad.status_code == 400
        assert bad.json() == {"detail": "Only name, aliases and tags can be changed."}
