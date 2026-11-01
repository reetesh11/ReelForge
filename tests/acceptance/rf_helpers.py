"""Helpers for the acceptance tests. Public surfaces only; imports are lazy so a
missing module fails the individual test that needs it."""

from __future__ import annotations

import asyncio
import json
import os
import queue
import signal
import socket
import subprocess
import threading
import time
import urllib.request
from collections.abc import Callable
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]

MODELS_TOML = """\
[models.image]
id = "{image}"
revision = "r1"
license = "mit"
license_url = "https://example.invalid/mit"

[models.video]
id = "test-org/video-model-xyz"
revision = "r2"
license = "mit"
license_url = "https://example.invalid/mit"

[models.tts]
id = "test-org/tts-model-xyz"
revision = "r3"
license = "mit"
license_url = "https://example.invalid/mit"

[models.llm]
id = "test-org/llm-model-xyz"
revision = "r4"
license = "mit"
license_url = "https://example.invalid/mit"
"""


def write_models(path: Path, image: str = "test-org/image-model-xyz") -> Path:
    path.write_text(MODELS_TOML.format(image=image))
    return path


def make_settings(tmp_path: Path, **over: Any):
    from reelforge.config import Settings

    base: dict[str, Any] = {
        "data_root": tmp_path / "data",
        "worker_poll_s": 0.05,
        "sample_interval_s": 0.1,
        "command_timeout_s": 60.0,
        "preflight_wait_s": 0.0,
        "health_poll_s": 3600.0,
    }
    base.update(over)
    return Settings(**base)


def passing_report(fail: dict[str, str] | None = None):
    """DoctorReport with all 11 checks passing; `fail` maps name -> severity."""
    from reelforge.doctor import CHECKS, CheckResult, DoctorReport

    fail = fail or {}
    checks = []
    for name in CHECKS:
        if name in fail:
            checks.append(
                CheckResult(
                    name=name,
                    status="fail",
                    severity=fail[name],  # type: ignore[arg-type]
                    detail=f"{name} broke",
                    fix=f"fix {name}",
                )
            )
        else:
            checks.append(
                CheckResult(name=name, status="pass", severity="blocking", detail="ok", fix=None)
            )
    return DoctorReport(checks=checks)


async def _noop_unload() -> None:
    return None


def make_ctx(
    settings,
    *,
    available_gb: float | Callable[[], float] = 64.0,
    adapter=None,
    unload=None,
    doctor=None,
):
    from reelforge.context import AppContext

    avail = available_gb if callable(available_gb) else (lambda: float(available_gb))
    return AppContext.create(
        settings,
        adapter=adapter,
        available_gb=avail,
        ollama_unload=unload or _noop_unload,
        doctor=doctor or (lambda: passing_report()),
    )


def make_client(ctx, *, start_worker: bool = True):
    from fastapi.testclient import TestClient
    from reelforge.api.app import create_app

    return TestClient(create_app(ctx, start_worker=start_worker))


def create_project(client, title: str = "Tomato tale") -> dict[str, Any]:
    r = client.post("/api/v1/projects", json={"title": title})
    assert r.status_code == 201, r.text
    return r.json()


def artifact_body(**over: Any) -> dict[str, Any]:
    body: dict[str, Any] = {
        "owner_type": "character",
        "owner_id": "own1",
        "kind": "candidate",
        "media": "image",
        "prompt": "a happy tomato",
        "seed": 1,
    }
    body.update(over)
    return body


def submit(client, project_id: str, **over: Any) -> dict[str, Any]:
    r = client.post(f"/api/v1/projects/{project_id}/artifacts", json=artifact_body(**over))
    assert r.status_code == 202, r.text
    return r.json()


def wait_job(ctx, job_id: str, statuses: set[str], timeout: float = 25.0):
    deadline = time.monotonic() + timeout
    job = ctx.queue.get(job_id)
    while time.monotonic() < deadline:
        job = ctx.queue.get(job_id)
        if job.status in statuses:
            return job
        time.sleep(0.03)
    raise AssertionError(
        f"job {job_id} stuck at {job.status!r} (wanted {statuses}); error={job.error!r}"
    )


def artifacts_of(ctx, project_id: str):
    from reelforge.db.models import Artifact
    from sqlalchemy import select

    with ctx.session_factory() as s:
        return list(
            s.scalars(
                select(Artifact).where(Artifact.project_id == project_id).order_by(Artifact.take_no)
            )
        )


def sidecar_of(ctx, artifact) -> dict[str, Any]:
    p = ctx.store.absolute_path(artifact)
    return json.loads(p.with_suffix(".json").read_text())


def store_bytes(
    ctx, project_id: str, data: bytes = b"hello world", *, ext: str = "png", **over: Any
):
    """Write an artifact directly through the store (no job)."""
    from reelforge.artifacts.store import ArtifactSpec

    kw: dict[str, Any] = {
        "project_id": project_id,
        "owner_type": "character",
        "owner_id": "own1",
        "kind": "candidate",
        "subdir": "candidates",
        "prompt": "a happy tomato",
        "seed": 7,
        "model_key": "image",
        "model_revision": "r1",
        "adapter": "mock",
        "version": "mock-1",
        "params": {},
        "width": None,
        "height": None,
        "duration_s": None,
    }
    kw.update(over)
    spec = ArtifactSpec(**kw)
    return spec, ctx.store.write(spec, data, ext=ext)


class CountingAdapter:
    """Delegates to MockAdapter and counts run() calls."""

    def __init__(self, settings) -> None:
        from reelforge.adapters.mock import MockAdapter
        from reelforge.models_registry import load_models

        self.inner = MockAdapter(
            load_models(settings.models_path),
            default_timeout_s=settings.command_timeout_s,
            sample_interval_s=settings.sample_interval_s,
        )
        self.name = self.inner.name
        self.version = self.inner.version
        self.runs = 0

    async def health(self):
        return await self.inner.health()

    async def capabilities(self):
        return await self.inner.capabilities()

    async def run(self, task, out_dir, progress, cancel, *, ctx_job_id=None):
        self.runs += 1
        return await self.inner.run(task, out_dir, progress, cancel, ctx_job_id=ctx_job_id)


class WsCollector:
    def __init__(self, client) -> None:
        self._cm = client.websocket_connect("/ws/events")
        self._ws = self._cm.__enter__()
        self.q: queue.Queue[dict[str, Any]] = queue.Queue()
        self.seen: list[dict[str, Any]] = []
        threading.Thread(target=self._pump, daemon=True).start()

    def _pump(self) -> None:
        try:
            while True:
                self.q.put(self._ws.receive_json())
        except Exception:  # noqa: BLE001
            return

    def wait_for(
        self, pred: Callable[[dict[str, Any]], bool], timeout: float = 25.0
    ) -> dict[str, Any]:
        for m in self.seen:
            if pred(m):
                return m
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            try:
                m = self.q.get(timeout=0.1)
            except queue.Empty:
                continue
            self.seen.append(m)
            if pred(m):
                return m
        raise AssertionError(f"event not received; saw {[m.get('type') for m in self.seen]}")

    def close(self) -> None:
        try:
            self._cm.__exit__(None, None, None)
        except Exception:  # noqa: BLE001, S110
            pass


def run_async(coro):
    return asyncio.run(coro)


def free_port() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


_OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}))


def http_json(method: str, url: str, body: dict | None = None, timeout: float = 5.0):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(
        url, data=data, method=method, headers={"Content-Type": "application/json"}
    )
    with _OPENER.open(req, timeout=timeout) as resp:
        raw = resp.read()
        return resp.status, (json.loads(raw) if raw else None)


class UpProcess:
    """`reelforge up --allow-degraded --backend mock` as a real subprocess."""

    def __init__(self, data_root: Path, port: int) -> None:
        self.data_root = data_root
        self.port = port
        self.url = f"http://127.0.0.1:{port}"
        self.proc = subprocess.Popen(
            [
                "uv",
                "run",
                "reelforge",
                "up",
                "--allow-degraded",
                "--backend",
                "mock",
                "--data-root",
                str(data_root),
                "--api-port",
                str(port),
            ],
            cwd=REPO_ROOT,
            start_new_session=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )

    def wait_ready(self, timeout: float = 90.0) -> None:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if self.proc.poll() is not None:
                raise AssertionError(f"reelforge up exited early with {self.proc.returncode}")
            try:
                status, _ = http_json("GET", f"{self.url}/health", timeout=2.0)
                if status == 200:
                    return
            except Exception:  # noqa: BLE001
                time.sleep(0.3)
        raise AssertionError("server did not become ready")

    def kill_hard(self) -> None:
        try:
            os.killpg(self.proc.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        self.proc.wait(timeout=10)

    def stop(self) -> None:
        try:
            os.killpg(self.proc.pid, signal.SIGTERM)
        except ProcessLookupError:
            return
        try:
            self.proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            self.kill_hard()
