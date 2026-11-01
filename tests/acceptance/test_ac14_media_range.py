"""AC-14: /media honours Range."""

from __future__ import annotations

from rf_helpers import create_project, make_client, make_ctx, make_settings, store_bytes

DATA = bytes(i % 251 for i in range(1000))


def _setup(tmp_path):
    ctx = make_ctx(make_settings(tmp_path))
    client = make_client(ctx, start_worker=False)
    client.__enter__()
    pid = create_project(client)["id"]
    _, art = store_bytes(ctx, pid, DATA, ext="png")
    return ctx, client, art


def _done(ctx, client):
    client.__exit__(None, None, None)
    ctx.close()


def test_full_body_without_range(tmp_path):
    ctx, client, art = _setup(tmp_path)
    r = client.get(f"/media/{art.id}")
    assert r.status_code == 200 and r.content == DATA
    assert r.headers["accept-ranges"] == "bytes"
    assert r.headers["content-length"] == "1000"
    assert r.headers["content-type"].startswith("image/png")
    _done(ctx, client)


def test_range_first_hundred_bytes(tmp_path):
    ctx, client, art = _setup(tmp_path)
    r = client.get(f"/media/{art.id}", headers={"Range": "bytes=0-99"})
    assert r.status_code == 206
    assert r.content == DATA[0:100] and len(r.content) == 100
    assert r.headers["content-range"] == "bytes 0-99/1000"
    assert r.headers["accept-ranges"] == "bytes"
    _done(ctx, client)


def test_open_ended_and_suffix_ranges(tmp_path):
    ctx, client, art = _setup(tmp_path)
    r = client.get(f"/media/{art.id}", headers={"Range": "bytes=900-"})
    assert r.status_code == 206 and r.content == DATA[900:]
    assert r.headers["content-range"] == "bytes 900-999/1000"
    r = client.get(f"/media/{art.id}", headers={"Range": "bytes=-50"})
    assert r.status_code == 206 and r.content == DATA[-50:]
    assert r.headers["content-range"] == "bytes 950-999/1000"
    r = client.get(f"/media/{art.id}", headers={"Range": "bytes=10-19"})
    assert r.content == DATA[10:20] and r.headers["content-range"] == "bytes 10-19/1000"
    _done(ctx, client)


def test_unsatisfiable_range_is_416(tmp_path):
    ctx, client, art = _setup(tmp_path)
    r = client.get(f"/media/{art.id}", headers={"Range": "bytes=1000-1100"})
    assert r.status_code == 416
    assert r.headers["content-range"] == "bytes */1000"
    _done(ctx, client)
