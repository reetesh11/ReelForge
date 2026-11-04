"""Helpers for the M5 frames and shots acceptance tests. Public surfaces only."""

from __future__ import annotations

import asyncio
import json
import os
import stat
import subprocess
import sys
import time
import zlib
import struct
from pathlib import Path
from typing import Any

from m3_helpers import png_bytes
from m4_helpers import (
    LINES,
    PLENTY_GB,
    _MEMORY,
    action,
    cast_approved,
    set_presets,
)
from rf_helpers import CountingAdapter, make_client, make_ctx, make_settings, wait_job
from story_helpers import story_dict

TERMINAL = {"succeeded", "failed", "cancelled"}
SIDS = ["s1", "s2", "s3", "s4", "s5"]
TOMATO_LOOK = "round red tomato, big eyes, leaf hat, gold sherwani"
POTATO_LOOK = "chubby brown potato, moustache, pink turban, white kurta"


def base(pid: str) -> str:
    return f"/api/v1/projects/{pid}"


def story_text(asset: str | None = None, product_scene: str = "s2") -> str:
    """s1 tomato talks (medium), s2 potato talks (no framing, so closeup), s3 no line and two
    characters named in the action, s4 no line and continues from s3, s5 tomato talks."""
    d = story_dict(5, language="hindi")
    sc = d["scenes"]
    sc[0].update(speaker="tomato", line=LINES["s1"], duration=4.0, framing="medium")
    sc[1].update(speaker="potato", line=LINES["s2"], duration=4.0)
    sc[1].pop("framing", None)
    sc[2] = {"id": "s3", "setting": "Place 3", "action": "Tamatar and Aloo argue loudly",
             "framing": "wide", "duration": 3.0}
    sc[3] = {"id": "s4", "setting": "Place 4", "action": "The crowd cheers wildly",
             "framing": "medium", "continue_from": "s3", "duration": 3.0}
    sc[4].update(speaker="tomato", line=LINES["s5"], duration=4.0, framing="medium")
    if asset is not None:
        d["product"] = {"name": "Thekua", "asset": asset}
        for s in sc:
            if s["id"] == product_scene:
                s["product_in_shot"] = True
    return json.dumps(d, ensure_ascii=False)


class M5Adapter(CountingAdapter):
    """Mock adapter that records every task; can slow, fail or kill video jobs."""

    def __init__(self, settings) -> None:
        super().__init__(settings)
        self.tasks: list[tuple[str | None, Any]] = []
        self.sleep_s = 0.0
        self.video_fail: str | None = None
        self.video_exit: int | None = None
        self.active = 0
        self.max_active = 0

    async def run(self, task, out_dir, progress, cancel, *, ctx_job_id=None):
        self.tasks.append((ctx_job_id, task))
        if task.kind == "video" and self.video_fail:
            from reelforge.adapters.base import AdapterError

            raise AdapterError(self.video_fail)
        if task.kind in ("video", "image") and (self.sleep_s or self.video_exit):
            hooks = dict(task.params.get("mock") or {})
            if self.sleep_s:
                hooks["sleep_s"] = self.sleep_s
            if self.video_exit is not None and task.kind == "video":
                hooks["exit_code"] = self.video_exit
            task.params["mock"] = hooks
        self.active += 1
        self.max_active = max(self.max_active, self.active)
        try:
            return await super().run(task, out_dir, progress, cancel, ctx_job_id=ctx_job_id)
        finally:
            self.active -= 1

    def of_job(self, job_id: str):
        found = [t for j, t in self.tasks if j == job_id]
        assert found, f"adapter never saw job {job_id}"
        return found[-1]

    def video_tasks(self):
        return [(j, t) for j, t in self.tasks if t.kind == "video"]


class World:
    def __init__(self, tmp_path, **over) -> None:
        self.settings = make_settings(tmp_path, **over)
        self.adapter = M5Adapter(self.settings)
        self.box = {"gb": PLENTY_GB}
        self.unloads: list[float] = []

        async def unload():
            self.unloads.append(time.monotonic())

        self.ctx = make_ctx(
            self.settings, adapter=self.adapter, available_gb=lambda: self.box["gb"], unload=unload
        )
        _MEMORY[id(self.ctx)] = self.box
        self.client = make_client(self.ctx)
        self.data_root = Path(self.settings.data_root)

    def set_gb(self, gb: float) -> None:
        self.box["gb"] = gb


def world(tmp_path, **over) -> World:
    return World(tmp_path, **over)


def voices_approved(w: World, text: str | None = None) -> str:
    """Cast approved, voices rendered and approved: stage VOICES_APPROVED."""
    client, ctx = w.client, w.ctx
    pid = cast_approved(client, ctx, text=text or story_text())
    set_presets(client, pid)
    r = client.post(f"{base(pid)}/voices:generate", json={})
    assert r.status_code == 202, r.text
    job = wait_job(ctx, r.json()["id"], TERMINAL, timeout=90)
    assert job.status == "succeeded", job.error
    for sid in ("s1", "s2", "s5"):
        r = action(client, pid, sid, "approve")
        assert r.status_code == 200, r.text
    assert client.get(base(pid)).json()["stage"] == "VOICES_APPROVED"
    return pid


def wait_all(w: World, jobs: list[dict[str, Any]], timeout: float = 90.0) -> list[Any]:
    return [wait_job(w.ctx, j["id"], TERMINAL, timeout=timeout) for j in jobs]


def get_frames(w: World, pid: str) -> dict[str, Any]:
    r = w.client.get(f"{base(pid)}/frames")
    assert r.status_code == 200, r.text
    return r.json()


def frame(w: World, pid: str, sid: str) -> dict[str, Any]:
    return next(f for f in get_frames(w, pid)["frames"] if f["scene_id"] == sid)


def get_shots(w: World, pid: str) -> dict[str, Any]:
    r = w.client.get(f"{base(pid)}/shots")
    assert r.status_code == 200, r.text
    return r.json()


def shot(w: World, pid: str, sid: str) -> dict[str, Any]:
    return next(s for s in get_shots(w, pid)["shots"] if s["scene_id"] == sid)


def gen_frame(w: World, pid: str, sid: str):
    r = w.client.post(f"{base(pid)}/frames/{sid}:generate")
    assert r.status_code == 202, r.text
    return r.json(), wait_job(w.ctx, r.json()["id"], TERMINAL, timeout=60)


def frames_approved(w: World, pid: str) -> None:
    r = w.client.post(f"{base(pid)}/frames:generate", json={"mode": "missing"})
    assert r.status_code == 202, r.text
    for j in wait_all(w, r.json()["jobs"]):
        assert j.status == "succeeded", j.error
    for sid in SIDS:
        r = w.client.post(f"{base(pid)}/frames/{sid}:approve")
        assert r.status_code == 200, r.text
    assert w.client.get(base(pid)).json()["stage"] == "FRAMES_APPROVED"


def ready(w: World, *, asset: str | None = None) -> str:
    """Bring a world (inside `with w.client`) to FRAMES_APPROVED; returns the project id."""
    pid = voices_approved(w, story_text(asset))
    frames_approved(w, pid)
    return pid


def render_shot(w: World, pid: str, sid: str, what: str = "render"):
    r = w.client.post(f"{base(pid)}/shots/{sid}:{what}")
    assert r.status_code == 202, r.text
    return r.json(), wait_job(w.ctx, r.json()["id"], TERMINAL, timeout=90)


def render_all_shots(w: World, pid: str) -> None:
    """Render every shot (s4 continues from s3, so it goes last)."""
    r = w.client.post(f"{base(pid)}/shots:render-all", json={"mode": "missing"})
    assert r.status_code == 202, r.text
    for j in wait_all(w, r.json()["jobs"]):
        assert j.status == "succeeded", j.error
    if shot(w, pid, "s4")["state"] == "no_shot":
        _, j = render_shot(w, pid, "s4")
        assert j.status == "succeeded", j.error


def shots_approved(w: World, pid: str) -> None:
    render_all_shots(w, pid)
    for sid in SIDS:
        r = w.client.post(f"{base(pid)}/shots/{sid}:approve")
        assert r.status_code == 200, r.text
    assert w.client.get(base(pid)).json()["stage"] == "SHOTS_APPROVED"


def artifact(w: World, artifact_id: str):
    from reelforge.db.models import Artifact

    with w.ctx.session_factory() as s:
        a = s.get(Artifact, artifact_id)
        assert a is not None, artifact_id
        s.expunge(a)
        return a


def art_path(w: World, artifact_id: str) -> Path:
    return Path(w.ctx.store.absolute_path(artifact(w, artifact_id))).resolve()


def media_id(url: str) -> str:
    assert url.startswith("/media/"), url
    return url.removeprefix("/media/")


def active_take(card: dict[str, Any]) -> dict[str, Any]:
    act = [t for t in card["takes"] if t["active"]]
    assert len(act) == 1, card["takes"]
    return act[0]


def scene_row(w: World, pid: str, sid: str):
    from reelforge.db.models import Scene
    from sqlalchemy import select

    with w.ctx.session_factory() as s:
        return s.scalars(select(Scene).where(Scene.project_id == pid, Scene.story_key == sid)).one()


def edit_action(w: World, pid: str, sid: str, text: str) -> None:
    """Change a scene's action the way the story editor does, keeping the project stage."""
    from reelforge.story import service as story_service
    from reelforge.story.schema import Story  # noqa: F401

    cur = story_service.current_version(w.ctx, pid)
    d = json.loads(cur.yaml_text)
    for s in d["scenes"]:
        if s["id"] == sid:
            s["action"] = text
    story_service.save_version(w.ctx, pid, json.dumps(d, ensure_ascii=False), keep_stage=True)


def random_png(width: int, height: int) -> bytes:
    def chunk(tag: bytes, data: bytes) -> bytes:
        body = tag + data
        return struct.pack(">I", len(data)) + body + struct.pack(">I", zlib.crc32(body))

    raw = b"".join(b"\x00" + os.urandom(width * 3) for _ in range(height))
    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
        + chunk(b"IDAT", zlib.compress(raw, 1))
        + chunk(b"IEND", b"")
    )


def make_media(path: Path, args: list[str]) -> bytes:
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", *args, str(path)], check=True, timeout=120)
    return path.read_bytes()


def jpeg_bytes(tmp_path: Path) -> bytes:
    return make_media(tmp_path / "x.jpg", ["-f", "lavfi", "-i", "color=c=red:s=64x112", "-frames:v", "1"])


def mp4_bytes(tmp_path: Path, name: str = "c.mp4", size: str = "72x128", seconds: float = 1.0) -> bytes:
    return make_media(
        tmp_path / name,
        ["-f", "lavfi", "-i", f"testsrc=size={size}:rate=12:duration={seconds}", "-pix_fmt", "yuv420p"],
    )


def noisy_mp4_bytes(tmp_path: Path) -> bytes:
    return make_media(
        tmp_path / "noisy.mp4",
        ["-f", "lavfi", "-i", "nullsrc=s=144x256:r=24:d=6", "-vf", "geq=random(1)*255:128:128",
         "-c:v", "mpeg4", "-q:v", "2", "-pix_fmt", "yuv420p"],
    )


def ffprobe(path: Path) -> dict[str, Any]:
    res = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries",
         "stream=codec_type,width,height,nb_frames,r_frame_rate", "-of", "json", str(path)],
        capture_output=True, text=True, timeout=60, check=True,
    )
    return json.loads(res.stdout)


REQ = {
    "a2v": ["--prompt", "--output", "--audio", "--image", "--frame-rate", "--frames", "--width",
            "--height", "--model", "--seed", "--distilled", "--low-ram"],
    "generate": ["--prompt", "--output", "--image", "--frame-rate", "--frames", "--width",
                 "--height", "--model", "--seed", "--distilled", "--low-ram", "--no-audio"],
    "extend": ["--prompt", "--output", "--video", "--extend-frames", "--distilled", "--low-ram",
               "--image"],
}


def fake_ltx(project: Path, *, help_flags: dict[str, list[str]] | None = None, **cfg: Any) -> tuple[Path, Path]:
    """A `<project>/.venv/bin/ltx-2-mlx` script. Its `--help` per subcommand and its run
    behaviour come from fake_cfg.json next to it, so a test can change them. Returns
    (exe, call log); the log has one JSON argv per non-help call."""
    bindir = project / ".venv" / "bin"
    bindir.mkdir(parents=True, exist_ok=True)
    exe = bindir / "ltx-2-mlx"
    log = project / "calls.log"
    flags = help_flags if help_flags is not None else {k: list(v) for k, v in REQ.items()}
    (bindir / "fake_cfg.json").write_text(json.dumps({"help": flags, **cfg}))
    exe.write_text(
        f"#!{sys.executable}\n"
        "import sys, json, os, time, subprocess\n"
        "here = os.path.dirname(os.path.abspath(__file__))\n"
        "cfg = json.load(open(os.path.join(here, 'fake_cfg.json')))\n"
        "a = sys.argv[1:]\n"
        "sub = a[0] if a else ''\n"
        "if '--help' in a:\n"
        "    f = cfg['help'].get(sub)\n"
        "    if f is None:\n"
        "        sys.exit(2)\n"
        "    print('Usage: ltx-2-mlx ' + sub + ' [OPTIONS]')\n"
        "    for x in f:\n"
        "        print('  ' + x + ' TEXT  an option')\n"
        "    sys.exit(0)\n"
        f"open({str(log)!r}, 'a').write(json.dumps(a) + '\\n')\n"
        "mode = cfg.get('mode', 'ok')\n"
        "if mode == 'exit':\n"
        "    sys.stderr.write(cfg.get('stderr', '') + '\\n')\n"
        "    sys.exit(cfg['code'])\n"
        "if mode == 'kill':\n"
        "    os.kill(os.getpid(), 9)\n"
        "if mode == 'sleep':\n"
        "    time.sleep(60)\n"
        "out = a[a.index('--output') + 1]\n"
        "subprocess.run(['ffmpeg', '-y', '-loglevel', 'error', '-f', 'lavfi', '-i',\n"
        "    'testsrc=size=64x64:rate=24:duration=0.5', '-pix_fmt', 'yuv420p', out], check=True)\n"
    )
    exe.chmod(exe.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    return exe, log


def set_fake(project: Path, **cfg: Any) -> None:
    p = project / ".venv" / "bin" / "fake_cfg.json"
    data = json.loads(p.read_text())
    data.update(cfg)
    p.write_text(json.dumps(data))


def opt(argv: list[str], flag: str) -> str:
    return argv[argv.index(flag) + 1]


def calls(log: Path) -> list[list[str]]:
    if not log.exists():
        return []
    return [json.loads(x) for x in log.read_text().splitlines() if x.strip()]


def ltx_task(tmp_path: Path, mode: str = "a2v", steps: int | None = 8, **params: Any):
    from reelforge.adapters.base import TaskSpec
    from reelforge.models_registry import ModelEntry

    img = tmp_path / "in.png"
    img.write_bytes(png_bytes(9, 16))
    inputs = [img]
    if mode == "a2v":
        wav = tmp_path / "in.wav"
        wav.write_bytes(b"RIFF")
        inputs.append(wav)
    p = {"mode": mode, "fps": 24, "frames": 81, "width": 320, "height": 576}
    p.update(params)
    return TaskSpec(
        kind="video",
        prompt="a tomato waves",
        seed=77,
        params=p,
        model=ModelEntry(key="video", id="test-org/ltx-test", revision="r", steps=steps),
        input_paths=inputs,
    )


def run_ltx(adapter, task, tmp_path: Path, cancel=None):
    from reelforge.adapters.base import CancelToken

    return asyncio.run(
        adapter.run(task, tmp_path / "out", lambda pct, msg: None, cancel or CancelToken())
    )
