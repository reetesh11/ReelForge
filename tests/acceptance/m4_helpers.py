"""Helpers for the M4 voice acceptance tests. Public surfaces only."""

from __future__ import annotations

import io
import json
import math
import struct
import wave
from pathlib import Path
from typing import Any

from m3_helpers import RecAdapter, gen_and_approve
from rf_helpers import create_project, make_client, make_ctx, make_settings, wait_job
from story_helpers import put, story_dict

TERMINAL = {"succeeded", "failed", "cancelled"}
ROOT = Path(__file__).resolve().parents[2]
WORKER_SRC = ROOT / "src" / "reelforge" / "adapters" / "tts_worker.py"

LINES = {
    "s1": "Arre Aloo itni der kyun aaye ho aaj",
    "s2": "Mithai ke bina shaadi nahi hoti yaar",
    "s3": "Dekho dekho mithai aa gayi hai yahan",
    "s4": "Sab log taali bajao zor se abhi",
    "s5": "Chalo ab sab milkar thekua khaate hain",
}


def story_text(duration: float = 4.0) -> str:
    d = story_dict(5, language="hindi")
    for i, sc in enumerate(d["scenes"], start=1):
        sc["speaker"] = "tomato" if i % 2 else "potato"
        sc["line"] = LINES[f"s{i}"]
        sc["duration"] = duration
    return json.dumps(d, ensure_ascii=False)


def voice_world(tmp_path, available_gb: float = 64.0, unload=None, **over):
    settings = make_settings(tmp_path, **over)
    ctx = make_ctx(
        settings, adapter=RecAdapter(settings), available_gb=available_gb, unload=unload
    )
    return ctx, make_client(ctx)


def cast_approved(client, ctx, title: str = "Voice tale", text: str | None = None) -> str:
    pid = create_project(client, title)["id"]
    assert put(client, pid, text or story_text()).status_code == 200
    r = client.post(f"/api/v1/projects/{pid}/story:approve")
    assert r.status_code == 200, r.text
    gen_and_approve(client, ctx, pid, "tomato", seed=11)
    gen_and_approve(client, ctx, pid, "potato", seed=12)
    assert client.get(f"/api/v1/projects/{pid}").json()["stage"] == "CAST_APPROVED"
    return pid


def base(pid: str) -> str:
    return f"/api/v1/projects/{pid}"


def get_voices(client, pid: str) -> dict[str, Any]:
    r = client.get(f"{base(pid)}/voices")
    assert r.status_code == 200, r.text
    return r.json()


def line_of(client, pid: str, scene_id: str) -> dict[str, Any]:
    return next(x for x in get_voices(client, pid)["lines"] if x["scene_id"] == scene_id)


def set_presets(client, pid: str) -> None:
    for key, vid in (("tomato", "ravi"), ("potato", "asha")):
        r = client.post(f"{base(pid)}/voices/characters/{key}:set", json={"mode": "preset", "voice_id": vid})
        assert r.status_code == 200, r.text


def generate(client, ctx, pid: str, timeout: float = 90.0, **body: Any):
    r = client.post(f"{base(pid)}/voices:generate", json=body)
    assert r.status_code == 202, r.text
    return r.json(), wait_job(ctx, r.json()["id"], TERMINAL, timeout=timeout)


def action(client, pid: str, scene_id: str, name: str, **body: Any):
    return client.post(f"{base(pid)}/voices/lines/{scene_id}:{name}", json=body)


def rendered_project(client, ctx, **kw) -> str:
    pid = cast_approved(client, ctx, **kw)
    set_presets(client, pid)
    _, job = generate(client, ctx, pid)
    assert job.status == "succeeded", job.error
    return pid


def approve_all(client, pid: str) -> dict[str, Any]:
    last: dict[str, Any] = {}
    for sid in LINES:
        r = action(client, pid, sid, "approve")
        assert r.status_code == 200, r.text
        last = r.json()
    return last


def wav_bytes(seconds: float, rate: int = 24000, freq: float = 440.0, amp: float = 0.5) -> bytes:
    n = int(seconds * rate)
    frames = b"".join(
        struct.pack("<h", int(amp * 32767 * math.sin(2 * math.pi * freq * i / rate))) for i in range(n)
    )
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(frames)
    return buf.getvalue()


def read_wav(data_or_path) -> tuple[list[int], int, int, int]:
    src = io.BytesIO(data_or_path) if isinstance(data_or_path, bytes) else str(data_or_path)
    with wave.open(src, "rb") as w:
        raw = w.readframes(w.getnframes())
        samples = list(struct.unpack(f"<{len(raw) // 2}h", raw))
        return samples, w.getframerate(), w.getnchannels(), w.getsampwidth()


def wav_seconds(data_or_path) -> float:
    s, rate, _, _ = read_wav(data_or_path)
    return len(s) / rate


def wrap_worker(tmp_path, monkeypatch, body: str | None = None):
    from reelforge.adapters import mlx_audio

    real = str(mlx_audio.WORKER_PATH)
    log = tmp_path / "invocations.jsonl"
    script = tmp_path / "wrap_worker.py"
    if body is None:
        body = (
            "import runpy\n"
            f"sys.argv = [{real!r}] + a\n"
            f"runpy.run_path({real!r}, run_name='__main__')\n"
        )
    script.write_text(
        "import sys, json\n"
        "a = sys.argv[1:]\n"
        f"open({str(log)!r}, 'a').write(json.dumps({{'argv': a, 'batch': open(a[a.index('--batch')+1]).read()}}) + '\\n')\n"
        + body
    )
    monkeypatch.setattr(mlx_audio, "WORKER_PATH", script)
    return log
