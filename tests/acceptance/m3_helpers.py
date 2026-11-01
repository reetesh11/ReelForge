"""Helpers for the M3 cast acceptance tests. Public surfaces only."""

from __future__ import annotations

import base64
import json
import stat
import struct
import sys
import threading
import zlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

from rf_helpers import CountingAdapter, create_project, make_client, make_ctx, make_settings, wait_job
from story_helpers import STORY_YAML, put

TERMINAL = {"succeeded", "failed", "cancelled"}


def png_bytes(width: int = 8, height: int = 16, rgb: tuple[int, int, int] = (200, 30, 30)) -> bytes:
    def chunk(tag: bytes, data: bytes) -> bytes:
        body = tag + data
        return struct.pack(">I", len(data)) + body + struct.pack(">I", zlib.crc32(body))

    raw = (b"\x00" + bytes(rgb) * width) * height
    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
        + chunk(b"IDAT", zlib.compress(raw, 6))
        + chunk(b"IEND", b"")
    )


class RecAdapter(CountingAdapter):
    """Mock adapter that records every call; optional hook runs after each call."""

    def __init__(self, settings) -> None:
        super().__init__(settings)
        self.calls: list[dict[str, Any]] = []
        self.after = None

    async def run(self, task, out_dir, progress, cancel, *, ctx_job_id=None):
        self.calls.append(
            {
                "seed": task.seed,
                "prompt": task.prompt,
                "kind": task.kind,
                "inputs": list(task.input_paths),
                "model_id": task.model.id,
                "job_id": ctx_job_id,
            }
        )
        res = await super().run(task, out_dir, progress, cancel, ctx_job_id=ctx_job_id)
        if self.after is not None:
            self.after(len(self.calls), ctx_job_id)
        return res

    @property
    def seeds(self) -> list[int]:
        return [c["seed"] for c in self.calls]


def new_world(tmp_path, **settings_over):
    """Mock-backend app with a recording adapter. Returns (ctx, client, adapter)."""
    settings = make_settings(tmp_path, **settings_over)
    adapter = RecAdapter(settings)
    ctx = make_ctx(settings, adapter=adapter)
    return ctx, make_client(ctx), adapter


def approved_project(client, title: str = "Tomato tale") -> str:
    pid = create_project(client, title)["id"]
    assert put(client, pid, STORY_YAML).status_code == 200
    r = client.post(f"/api/v1/projects/{pid}/story:approve")
    assert r.status_code == 200, r.text
    return pid


def cast_url(pid: str, key: str | None = None, action: str | None = None) -> str:
    base = f"/api/v1/projects/{pid}/cast"
    if key is None:
        return base
    return f"{base}/{key}:{action}"


def get_cast(client, pid: str) -> dict[str, Any]:
    r = client.get(cast_url(pid))
    assert r.status_code == 200, r.text
    return r.json()


def cast_item(client, pid: str, key: str) -> dict[str, Any]:
    return next(c for c in get_cast(client, pid)["characters"] if c["key"] == key)


def generate(client, ctx, pid: str, key: str, timeout: float = 30.0, **body: Any):
    r = client.post(cast_url(pid, key, "generate"), json=body)
    assert r.status_code == 202, r.text
    return r.json(), wait_job(ctx, r.json()["id"], TERMINAL, timeout=timeout)


def approve(client, pid: str, key: str, candidate_id: str):
    return client.post(cast_url(pid, key, "approve"), json={"candidate_id": candidate_id})


def gen_and_approve(client, ctx, pid: str, key: str, **body: Any) -> dict[str, Any]:
    _, job = generate(client, ctx, pid, key, **body)
    assert job.status == "succeeded", job.error
    cand = cast_item(client, pid, key)["candidates"][0]
    r = approve(client, pid, key, cand["id"])
    assert r.status_code == 200, r.text
    return r.json()


class StubServer:
    """Loopback HTTP server standing in for Draw Things. Records POST requests."""

    def __init__(self, *, txt2img_status: int = 200, img2img_status: int = 200, root_status: int = 200):
        self.requests: list[dict[str, Any]] = []
        self.status = {
            "/sdapi/v1/txt2img": txt2img_status,
            "/sdapi/v1/img2img": img2img_status,
        }
        outer = self

        class H(BaseHTTPRequestHandler):
            def log_message(self, *a):  # noqa: D401
                return

            def do_GET(self):  # noqa: N802
                self.send_response(root_status)
                self.send_header("Content-Length", "2")
                self.end_headers()
                self.wfile.write(b"ok")

            def do_POST(self):  # noqa: N802
                n = int(self.headers.get("Content-Length") or 0)
                raw = self.rfile.read(n)
                try:
                    body = json.loads(raw)
                except ValueError:
                    body = None
                outer.requests.append({"path": self.path, "body": body})
                code = outer.status.get(self.path, 404)
                if code == 200:
                    payload = json.dumps(
                        {"images": [base64.b64encode(png_bytes(8, 16)).decode()]}
                    ).encode()
                else:
                    payload = b'{"detail":"nope"}'
                self.send_response(code)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)

        self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), H)
        self.port = self.httpd.server_address[1]
        self.url = f"http://127.0.0.1:{self.port}"
        self.thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)
        self.thread.start()

    def posts(self, path: str | None = None) -> list[dict[str, Any]]:
        return [r for r in self.requests if path is None or r["path"] == path]

    def close(self) -> None:
        self.httpd.shutdown()
        self.httpd.server_close()


def fake_mflux(dir_: Path) -> tuple[Path, Path]:
    """Executable that logs its argv (JSON per line) and writes a PNG to --output."""
    log = dir_ / "mflux_calls.log"
    script = dir_ / "fake_mflux"
    png = base64.b64encode(png_bytes(8, 16)).decode()
    script.write_text(
        f"#!{sys.executable}\n"
        "import sys, json, base64\n"
        "a = sys.argv[1:]\n"
        f"open({str(log)!r}, 'a').write(json.dumps(a) + '\\n')\n"
        "out = a[a.index('--output') + 1]\n"
        f"open(out, 'wb').write(base64.b64decode({png!r}))\n"
    )
    script.chmod(script.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    return script, log


def task_spec(*, seed: int = 5, prompt: str = "a red tomato", model_id: str = "pinned-model.ckpt",
              inputs: list[Path] | None = None, **params: Any):
    from reelforge.adapters.base import TaskSpec
    from reelforge.models_registry import ModelEntry

    return TaskSpec(
        kind="image",
        prompt=prompt,
        seed=seed,
        params=params,
        model=ModelEntry(key="image", id=model_id, revision="r1", license="mit", license_url=""),
        input_paths=inputs or [],
    )


def models_with_license(path: Path, license_: str, url: str = "https://example.invalid/lic") -> Path:
    from rf_helpers import MODELS_TOML

    text = MODELS_TOML.format(image="test-org/image-model-xyz").replace(
        'license = "mit"\nlicense_url = "https://example.invalid/mit"',
        f'license = "{license_}"\nlicense_url = "{url}"',
        1,
    )
    path.write_text(text)
    return path
