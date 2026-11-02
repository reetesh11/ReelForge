"""AC-9 (Draw Things adapter against a stub server, doctor 422), AC-12 (mflux adapter)."""

from __future__ import annotations

import base64
import json

import pytest
from m3_helpers import StubServer, fake_mflux, png_bytes, task_spec
from rf_helpers import free_port, make_settings, run_async, write_models


def _run(adapter, task, out_dir):
    from reelforge.adapters.base import CancelToken

    return run_async(adapter.run(task, out_dir, lambda pct, msg: None, CancelToken()))


@pytest.fixture
def stub():
    s = StubServer()
    yield s
    s.close()


def test_txt2img_one_request_pinned_model_no_batch(stub, tmp_path):
    from reelforge.adapters.drawthings import DrawThingsAdapter

    out = _run(DrawThingsAdapter(stub.url), task_spec(seed=11, prompt="red tomato"), tmp_path / "o")
    assert len(stub.requests) == 1
    req = stub.requests[0]
    assert req["path"] == "/sdapi/v1/txt2img"
    body = req["body"]
    assert body["model"] == "pinned-model.ckpt"
    assert body["prompt"] == "red tomato" and body["seed"] == 11
    assert (body["width"], body["height"], body["steps"]) == (576, 1024, 4)
    assert "batch_size" not in body and "batch_count" not in body
    assert len(out) == 1 and out[0].ext == "png"
    assert out[0].path.read_bytes()[:8] == b"\x89PNG\r\n\x1a\n"
    assert out[0].path.name == "out.png"


def test_params_override_size_and_steps(stub, tmp_path):
    from reelforge.adapters.drawthings import DrawThingsAdapter

    _run(DrawThingsAdapter(stub.url), task_spec(width=320, height=576, steps=2), tmp_path / "o")
    body = stub.requests[0]["body"]
    assert (body["width"], body["height"], body["steps"]) == (320, 576, 2)


def test_img2img_sends_init_image_and_strength(stub, tmp_path):
    from reelforge.adapters.drawthings import DrawThingsAdapter

    src = tmp_path / "in.png"
    src.write_bytes(png_bytes(4, 8))
    _run(DrawThingsAdapter(stub.url), task_spec(inputs=[src], strength=0.45), tmp_path / "o")
    assert len(stub.requests) == 1
    req = stub.requests[0]
    assert req["path"] == "/sdapi/v1/img2img"
    assert req["body"]["init_images"] == [base64.b64encode(src.read_bytes()).decode()]
    assert req["body"]["strength"] == 0.45
    assert "batch_size" not in req["body"] and "batch_count" not in req["body"]


def test_error_messages(tmp_path):
    from reelforge.adapters.base import AdapterError
    from reelforge.adapters.drawthings import DrawThingsAdapter

    s422 = StubServer(txt2img_status=422)
    try:
        with pytest.raises(AdapterError) as e:
            _run(DrawThingsAdapter(s422.url), task_spec(model_id="nope.ckpt"), tmp_path / "a")
        assert str(e.value) == "Draw Things doesn't have the model nope.ckpt"
    finally:
        s422.close()

    s404 = StubServer(img2img_status=404)
    try:
        src = tmp_path / "in.png"
        src.write_bytes(png_bytes(4, 8))
        with pytest.raises(AdapterError) as e:
            _run(DrawThingsAdapter(s404.url), task_spec(inputs=[src]), tmp_path / "b")
        assert str(e.value) == "This Draw Things setup can't edit images"
    finally:
        s404.close()

    s500 = StubServer(txt2img_status=500)
    try:
        with pytest.raises(AdapterError) as e:
            _run(DrawThingsAdapter(s500.url), task_spec(), tmp_path / "c")
        assert "500" in str(e.value)
    finally:
        s500.close()

    port = free_port()
    with pytest.raises(AdapterError) as e:
        _run(DrawThingsAdapter(f"http://127.0.0.1:{port}"), task_spec(), tmp_path / "d")
    assert str(e.value) == f"Draw Things isn't reachable on port {port}"


def _doctor_draw_things(monkeypatch, tmp_path, url: str):
    from reelforge.doctor import CHECKS, CheckResult, run_doctor

    for name in list(CHECKS):
        if name == "draw_things":
            continue

        def fn(settings, _n=name):
            return CheckResult(name=_n, status="pass", severity="blocking", detail="ok", fix=None)

        monkeypatch.setitem(CHECKS, name, fn)
    models = write_models(tmp_path / "models.toml", image="pinned-xyz.ckpt")
    report = run_doctor(make_settings(tmp_path, drawthings_url=url, models_path=models))
    assert len(report.checks) == 11
    return next(c for c in report.checks if c.name == "draw_things"), report


def test_doctor_fails_when_pinned_model_is_rejected_with_422(monkeypatch, tmp_path):
    s = StubServer(txt2img_status=422)
    try:
        check, report = _doctor_draw_things(monkeypatch, tmp_path, s.url)
    finally:
        s.close()
    assert check.status == "fail" and check.severity == "blocking"
    assert "pinned-xyz.ckpt" in check.detail
    assert report.ok is False


def test_doctor_passes_when_model_accepted(monkeypatch, tmp_path):
    s = StubServer(txt2img_status=200)
    try:
        check, report = _doctor_draw_things(monkeypatch, tmp_path, s.url)
        probes = s.posts("/sdapi/v1/txt2img")
    finally:
        s.close()
    assert check.status == "pass", check.detail
    assert len(probes) == 1 and probes[0]["body"]["model"] == "pinned-xyz.ckpt"


def test_mflux_adapter_runs_argument_list(tmp_path):
    from reelforge.adapters.mflux import MfluxAdapter

    cmd, log = fake_mflux(tmp_path)
    out_dir = tmp_path / "out"
    out = _run(
        MfluxAdapter(cmd),
        task_spec(seed=7, prompt="red tomato", model_id="m-id", width=512, height=768, steps=3),
        out_dir,
    )
    lines = [json.loads(ln) for ln in log.read_text().splitlines()]
    assert lines == [
        [
            "--model", "m-id", "--prompt", "red tomato", "--seed", "7",
            "--width", "512", "--height", "768", "--steps", "3",
            "--output", str(out_dir / "out.png"),
        ]
    ]
    assert len(out) == 1 and out[0].ext == "png" and out[0].path == out_dir / "out.png"
    assert out[0].path.exists()


def test_mflux_adapter_img2img_flags_and_failure(tmp_path):
    from reelforge.adapters.base import AdapterError
    from reelforge.adapters.mflux import MfluxAdapter

    cmd, log = fake_mflux(tmp_path)
    src = tmp_path / "in.png"
    src.write_bytes(png_bytes(4, 8))
    _run(MfluxAdapter(cmd), task_spec(inputs=[src], strength=0.5, width=8, height=16, steps=1), tmp_path / "o")
    argv = json.loads(log.read_text().splitlines()[0])
    assert argv[-4:] == ["--image-path", str(src), "--image-strength", "0.5"]

    bad = tmp_path / "bad_mflux"
    bad.write_text("#!/bin/sh\nexit 3\n")
    bad.chmod(0o755)
    with pytest.raises(AdapterError):
        _run(MfluxAdapter(bad), task_spec(), tmp_path / "o2")
