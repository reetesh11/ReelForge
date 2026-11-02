"""m3b: Kontext default, per-model steps, Draw Things doctor probe (public surfaces only)."""

from __future__ import annotations

import base64
import json
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest
from m3_helpers import (
    StubServer,
    approve,
    approved_project,
    cast_item,
    cast_url,
    generate,
    png_bytes,
)
from rf_helpers import (
    artifacts_of,
    make_client,
    make_ctx,
    make_settings,
    run_async,
    sidecar_of,
)

KONTEXT_ID = "flux_1_kontext_dev_q8p.ckpt"
KONTEXT_LICENCE = "FLUX.1 Kontext [dev] Non-Commercial License"
PACKAGED = Path(__file__).resolve().parents[2] / "src" / "reelforge" / "models.toml"


class SizeAwareStub:
    """Draw Things stand-in: 422 when width or height < 128 or the model is not in `known`."""

    def __init__(self, known: set[str], delay_s: float = 0.0):
        self.requests: list[dict] = []
        outer = self

        class H(BaseHTTPRequestHandler):
            def log_message(self, *a):
                return

            def do_GET(self):  # noqa: N802
                self.send_response(200)
                self.send_header("Content-Length", "2")
                self.end_headers()
                self.wfile.write(b"ok")

            def do_POST(self):  # noqa: N802
                n = int(self.headers.get("Content-Length") or 0)
                body = json.loads(self.rfile.read(n))
                outer.requests.append(body)
                if delay_s:
                    time.sleep(delay_s)
                bad = (
                    int(body.get("width", 0)) < 128
                    or int(body.get("height", 0)) < 128
                    or body.get("model") not in known
                )
                if bad:
                    payload, code = b'{"detail":"nope"}', 422
                else:
                    payload = json.dumps(
                        {"images": [base64.b64encode(png_bytes(8, 16)).decode()]}
                    ).encode()
                    code = 200
                try:
                    self.send_response(code)
                    self.send_header("Content-Length", str(len(payload)))
                    self.end_headers()
                    self.wfile.write(payload)
                except OSError:
                    pass

        self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), H)
        self.url = f"http://127.0.0.1:{self.httpd.server_address[1]}"
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()

    def close(self):
        self.httpd.shutdown()
        self.httpd.server_close()


@pytest.fixture(autouse=True)
def _fresh_model_cache():
    import reelforge.adapters.drawthings as dt

    dt._model_ok.clear()
    yield
    dt._model_ok.clear()


# ---- AC-1: doctor probe ----------------------------------------------------------------------


def test_probe_is_128_by_128_one_step():
    from reelforge.adapters.drawthings import DrawThingsAdapter

    s = StubServer()
    try:
        DrawThingsAdapter(s.url, model_id="m.ckpt").check()
        probes = s.posts("/sdapi/v1/txt2img")
    finally:
        s.close()
    assert len(probes) == 1
    body = probes[0]["body"]
    assert (body["width"], body["height"], body["steps"]) == (128, 128, 1)
    assert body["model"] == "m.ckpt" and body["seed"] == 0 and body["prompt"] == "health check"


def test_check_passes_for_known_model_against_size_strict_stub():
    from reelforge.adapters.drawthings import DrawThingsAdapter

    s = SizeAwareStub({"good.ckpt"})
    try:
        rep = DrawThingsAdapter(s.url, model_id="good.ckpt").check()
    finally:
        s.close()
    assert rep.ok is True, rep.detail


# ---- AC-2: steps precedence ------------------------------------------------------------------


def _run(adapter, task, out_dir):
    from reelforge.adapters.base import CancelToken

    return run_async(adapter.run(task, out_dir, lambda pct, msg: None, CancelToken()))


def _task(steps_entry, inputs=None, **params):
    from reelforge.adapters.base import TaskSpec
    from reelforge.models_registry import ModelEntry

    return TaskSpec(
        kind="image",
        prompt="p",
        seed=1,
        params=params,
        model=ModelEntry(key="image", id="m.ckpt", revision="r", steps=steps_entry),
        input_paths=inputs or [],
    )


@pytest.mark.parametrize("img2img", [False, True])
def test_steps_precedence_task_then_entry_then_four(tmp_path, img2img):
    from reelforge.adapters.drawthings import DrawThingsAdapter

    inputs = []
    if img2img:
        src = tmp_path / "in.png"
        src.write_bytes(png_bytes(4, 8))
        inputs = [src]
    path = "/sdapi/v1/img2img" if img2img else "/sdapi/v1/txt2img"
    s = StubServer()
    try:
        ad = DrawThingsAdapter(s.url)
        _run(ad, _task(20, inputs), tmp_path / "a")
        _run(ad, _task(20, inputs, steps=7), tmp_path / "b")
        _run(ad, _task(None, inputs), tmp_path / "c")
        steps = [r["body"]["steps"] for r in s.posts(path)]
    finally:
        s.close()
    assert steps == [20, 7, 4]


def test_model_entry_steps_validation_and_loading(tmp_path):
    from pydantic import ValidationError

    from reelforge.models_registry import ModelEntry, load_models

    assert ModelEntry(key="k", id="i", revision="r", steps=20).steps == 20
    assert ModelEntry(key="k", id="i", revision="r").steps is None
    for bad in (0, -1, "many"):
        with pytest.raises(ValidationError):
            ModelEntry(key="k", id="i", revision="r", steps=bad)
    good = tmp_path / "good.toml"
    good.write_text('[models.image]\nid = "a"\nrevision = "r"\nsteps = 12\n')
    assert load_models(good).get("image").steps == 12
    badf = tmp_path / "bad.toml"
    badf.write_text('[models.image]\nid = "a"\nrevision = "r"\nsteps = 0\n')
    with pytest.raises(ValidationError):
        load_models(badf)


# ---- AC-3: packaged registry + cast job ------------------------------------------------------


def test_packaged_image_entry():
    from reelforge.models_registry import load_models

    e = load_models(PACKAGED).get("image")
    assert e.id == KONTEXT_ID and e.steps == 20 and e.revision == "unpinned"
    assert e.license == KONTEXT_LICENCE
    assert e.license_url == "https://huggingface.co/black-forest-labs/FLUX.1-Kontext-dev"


def test_cast_generate_and_refine_send_kontext_model_and_20_steps(tmp_path):
    s = StubServer()
    try:
        settings = make_settings(tmp_path, backend="real", drawthings_url=s.url)
        ctx = make_ctx(settings)
        client = make_client(ctx)
        with client:
            pid = approved_project(client)
            _, job = generate(client, ctx, pid, "tomato", seed=3)
            assert job.status == "succeeded", job.error
            cand = cast_item(client, pid, "tomato")["candidates"][0]
            _, job2 = generate(
                client,
                ctx,
                pid,
                "tomato",
                refine={"from_candidate": cand["id"], "instruction": "smaller"},
            )
            assert job2.status == "succeeded", job2.error
        txt = s.posts("/sdapi/v1/txt2img")
        img = s.posts("/sdapi/v1/img2img")
    finally:
        s.close()
    assert txt and img
    for r in txt + img:
        assert r["body"]["model"] == KONTEXT_ID
        assert r["body"]["steps"] == 20


# ---- AC-4 / AC-5: licence --------------------------------------------------------------------


def test_packaged_registry_warns_in_health_and_cast_and_sidecars_record_licence(tmp_path):
    ctx = make_ctx(make_settings(tmp_path))
    client = make_client(ctx)
    with client:
        pid = approved_project(client)
        warn = client.get("/health").json().get("image_licence_warning")
        assert warn and KONTEXT_LICENCE in warn
        assert client.get(cast_url(pid)).json().get("licence_warning") == warn
        _, job = generate(client, ctx, pid, "tomato", seed=2)
        assert job.status == "succeeded", job.error
        cands = cast_item(client, pid, "tomato")["candidates"]
        assert cands
        for c in cands:
            art = next(a for a in artifacts_of(ctx, pid) if a.id == c["id"])
            assert sidecar_of(ctx, art)["license"] == KONTEXT_LICENCE
        assert approve(client, pid, "tomato", cands[0]["id"]).status_code == 200
