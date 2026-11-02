"""Draw Things adapter against a loopback stub (see also the M3 acceptance tests)."""

from __future__ import annotations

import base64
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

import pytest

from reelforge.adapters.base import AdapterError, CancelToken, TaskSpec
from reelforge.adapters.drawthings import DrawThingsAdapter, unreachable_message
from reelforge.models_registry import ModelEntry

PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
)


class Stub:
    def __init__(self, status: int = 200) -> None:
        self.posts: list[dict[str, Any]] = []
        outer = self

        class H(BaseHTTPRequestHandler):
            def log_message(self, *a: Any) -> None:
                return

            def do_GET(self) -> None:  # noqa: N802
                self.send_response(200)
                self.send_header("Content-Length", "0")
                self.end_headers()

            def do_POST(self) -> None:  # noqa: N802
                raw = self.rfile.read(int(self.headers.get("Content-Length") or 0))
                outer.posts.append({"path": self.path, "body": json.loads(raw)})
                payload = json.dumps({"images": [base64.b64encode(PNG).decode()]}).encode()
                if status != 200:
                    payload = b"{}"
                self.send_response(status)
                self.send_header("Content-Length", str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)

        self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), H)
        self.url = f"http://127.0.0.1:{self.httpd.server_address[1]}"
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()

    def close(self) -> None:
        self.httpd.shutdown()
        self.httpd.server_close()


def _task(**params: Any) -> TaskSpec:
    model = ModelEntry(key="image", id="m.ckpt", revision="r", license="mit")
    return TaskSpec(kind="image", prompt="p", seed=3, params=params, model=model)


@pytest.fixture
def stub():
    s = Stub()
    yield s
    s.close()


async def test_txt2img_has_model_and_no_batch(stub, tmp_path):
    adapter = DrawThingsAdapter(stub.url)
    out = await adapter.run(_task(), tmp_path, lambda p, m: None, CancelToken())
    body = stub.posts[0]["body"]
    assert stub.posts[0]["path"] == "/sdapi/v1/txt2img"
    assert body["model"] == "m.ckpt" and "batch_size" not in body and "batch_count" not in body
    assert (out[0].width, out[0].height) == (1, 1)


async def test_cancel_before_response(tmp_path):
    token = CancelToken()
    token.cancel()
    s = Stub()
    try:
        with pytest.raises(AdapterError, match="cancelled"):
            await DrawThingsAdapter(s.url).run(_task(), tmp_path, lambda p, m: None, token)
    finally:
        s.close()


def test_unreachable_message_uses_port():
    assert unreachable_message("http://127.0.0.1:7861") == (
        "Draw Things isn't reachable on port 7861"
    )
    assert unreachable_message("http://127.0.0.1") == "Draw Things isn't reachable on port 7860"


def test_check_model_422_fails_and_success_is_cached():
    bad = Stub(status=422)
    good = Stub()
    try:
        rep = DrawThingsAdapter(bad.url, model_id="m.ckpt").check()
        assert rep.ok is False and "m.ckpt" in rep.detail
        assert DrawThingsAdapter(good.url, model_id="m.ckpt").check().ok is True
        assert DrawThingsAdapter(good.url, model_id="m.ckpt").check().ok is True
        assert len(good.posts) == 1
    finally:
        bad.close()
        good.close()


def test_model_probe_respects_draw_things_minimum_size():
    # The real server answers 422 for any width or height below 128, whatever the model.
    good = Stub()
    try:
        assert DrawThingsAdapter(good.url, model_id="probe-size.ckpt").check().ok is True
        body = good.posts[0]["body"]
        assert body["width"] >= 128 and body["height"] >= 128
    finally:
        good.close()


def _task_steps(
    entry_steps: int | None, input_paths: list | None = None, **params: Any
) -> TaskSpec:
    model = ModelEntry(key="image", id="m.ckpt", revision="r", license="mit", steps=entry_steps)
    return TaskSpec(
        kind="image", prompt="p", seed=3, params=params, model=model, input_paths=input_paths or []
    )


def test_probe_is_128_one_step():
    s = Stub()
    try:
        assert DrawThingsAdapter(s.url, model_id="probe-128.ckpt").check().ok is True
        body = s.posts[0]["body"]
        assert (body["width"], body["height"], body["steps"]) == (128, 128, 1)
    finally:
        s.close()


@pytest.mark.parametrize(
    ("entry", "params", "expected"),
    [(20, {}, 20), (20, {"steps": 8}, 8), (None, {}, 4)],
)
async def test_body_steps_precedence(stub, tmp_path, entry, params, expected):
    await DrawThingsAdapter(stub.url).run(
        _task_steps(entry, **params), tmp_path, lambda p, m: None, CancelToken()
    )
    assert stub.posts[0]["body"]["steps"] == expected


async def test_img2img_uses_entry_steps(stub, tmp_path):
    img = tmp_path / "in.png"
    img.write_bytes(PNG)
    await DrawThingsAdapter(stub.url).run(
        _task_steps(20, [img]), tmp_path, lambda p, m: None, CancelToken()
    )
    assert stub.posts[0]["path"] == "/sdapi/v1/img2img"
    assert stub.posts[0]["body"]["steps"] == 20
