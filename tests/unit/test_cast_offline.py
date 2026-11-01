"""Generate, approve and reuse on the mock backend with every non-loopback connection blocked."""

from __future__ import annotations

import ipaddress
import socket
import time
from typing import Any

import pytest
import yaml_samples as ys
from _helpers import make_client, make_ctx


def _loopback(host: object) -> bool:
    if isinstance(host, bytes):
        host = host.decode()
    if not isinstance(host, str) or host in {"localhost", ""}:
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


@pytest.fixture(autouse=True)
def _no_outbound(monkeypatch: pytest.MonkeyPatch) -> None:
    real = socket.socket.connect

    def connect(self: socket.socket, address: Any) -> None:
        if isinstance(address, tuple) and address and not _loopback(address[0]):
            raise AssertionError(f"outbound network blocked: {address!r}")
        return real(self, address)

    monkeypatch.setattr(socket.socket, "connect", connect)


def _story_project(client) -> str:
    pid = client.post("/api/v1/projects", json={"title": "T"}).json()["id"]
    client.put(
        f"/api/v1/projects/{pid}/story",
        content=ys.STORY.encode(),
        headers={"Content-Type": "text/plain"},
    )
    assert client.post(f"/api/v1/projects/{pid}/story:approve").status_code == 200
    return pid


def _generate(client, ctx, pid: str) -> list[dict[str, Any]]:
    r = client.post(f"/api/v1/projects/{pid}/cast/tomato:generate", json={"seed": 3})
    assert r.status_code == 202
    deadline = time.monotonic() + 20
    while ctx.queue.get(r.json()["id"]).status not in {"succeeded", "failed", "cancelled"}:
        assert time.monotonic() < deadline
        time.sleep(0.03)
    assert ctx.queue.get(r.json()["id"]).status == "succeeded"
    return client.get(f"/api/v1/projects/{pid}/cast").json()["characters"][0]["candidates"]


def test_generate_approve_and_reuse_work_offline(tmp_path):
    ctx = make_ctx(tmp_path)
    with make_client(ctx) as client:
        a = _story_project(client)
        cands = _generate(client, ctx, a)
        assert len(cands) == 4
        r = client.post(
            f"/api/v1/projects/{a}/cast/tomato:approve", json={"candidate_id": cands[0]["id"]}
        )
        assert r.status_code == 200 and r.json()["project_stage"] == "CAST_APPROVED"
        lib = client.get("/api/v1/library/characters").json()
        assert len(lib) == 1

        b = _story_project(client)
        r = client.post(
            f"/api/v1/projects/{b}/cast/tomato:use-library", json={"character_id": lib[0]["id"]}
        )
        assert r.status_code == 200
        assert r.json()["character"]["master_sha256"] == lib[0]["master_sha256"]
        assert r.json()["project_stage"] == "CAST_APPROVED"
