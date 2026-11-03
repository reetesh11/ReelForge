"""m3b: behaviour that must not change (green before and after)."""

from __future__ import annotations

import base64
import json
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest
from m3_helpers import (
    approve,
    approved_project,
    cast_item,
    cast_url,
    generate,
    models_with_license,
    png_bytes,
)
from rf_helpers import (
    make_client,
    make_ctx,
    make_settings,
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


def test_check_fails_with_message_when_model_rejected():
    from reelforge.adapters.drawthings import DrawThingsAdapter

    s = SizeAwareStub({"good.ckpt"})
    try:
        rep = DrawThingsAdapter(s.url, model_id="other.ckpt").check()
    finally:
        s.close()
    assert rep.ok is False
    assert rep.detail == "Draw Things doesn't have the model other.ckpt"


def test_check_timeout_counts_as_ok(monkeypatch):
    import reelforge.adapters.drawthings as dt

    monkeypatch.setattr(dt, "MODEL_CHECK_TIMEOUT_S", 0.3)
    s = SizeAwareStub({"good.ckpt"}, delay_s=1.5)
    try:
        rep = dt.DrawThingsAdapter(s.url, model_id="good.ckpt").check()
    finally:
        s.close()
    assert rep.ok is True, rep.detail


def test_explicit_permissive_model_has_no_warning(tmp_path):
    models = models_with_license(tmp_path / "models.toml", "Apache-2.0")
    ctx = make_ctx(make_settings(tmp_path, models_path=models))
    client = make_client(ctx)
    with client:
        pid = approved_project(client)
        assert "image_licence_warning" not in client.get("/health").json()
        assert "licence_warning" not in client.get(cast_url(pid)).json()
        _, job = generate(client, ctx, pid, "tomato", seed=2)
        assert job.status == "succeeded", job.error
        cand = cast_item(client, pid, "tomato")["candidates"][0]
        assert approve(client, pid, "tomato", cand["id"]).status_code == 200
