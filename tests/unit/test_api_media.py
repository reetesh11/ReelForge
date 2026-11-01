from _helpers import make_client, make_ctx

from reelforge.api.routes_media import parse_range


def test_parse_range():
    assert parse_range("bytes=0-99", 1000) == (0, 99)
    assert parse_range("bytes=900-", 1000) == (900, 999)
    assert parse_range("bytes=-50", 1000) == (950, 999)
    assert parse_range("bytes=0-5000", 1000) == (0, 999)
    assert parse_range("bytes=1000-", 1000) == "unsatisfiable"
    assert parse_range("bytes=5-2", 1000) is None
    assert parse_range("garbage", 1000) is None


def test_media_confinement_and_ranges(tmp_path):
    from reelforge.artifacts.store import ArtifactSpec
    from reelforge.db.models import Artifact

    ctx = make_ctx(tmp_path)
    with make_client(ctx, start_worker=False) as c:
        pid = c.post("/api/v1/projects", json={"title": "T"}).json()["id"]
        art = ctx.store.write(
            ArtifactSpec(
                project_id=pid, owner_type="c", owner_id="o", kind="k", subdir="s", prompt="p",
                seed=1, model_key="image", model_revision="r", adapter="mock", version="v",
            ),
            b"0123456789",
            ext="png",
        )  # fmt: skip
        r = c.get(f"/media/{art.id}", headers={"Range": "bytes=2-4"})
        assert r.status_code == 206 and r.content == b"234"
        assert c.get(f"/media/{art.id}", headers={"Range": "bytes=50-"}).status_code == 416
        outside = tmp_path / "secret.txt"
        outside.write_text("x")
        with ctx.session_factory.begin() as s:
            s.get(Artifact, art.id).path = "../../secret.txt"  # type: ignore[union-attr]
        assert c.get(f"/media/{art.id}").status_code == 403
    ctx.close()
