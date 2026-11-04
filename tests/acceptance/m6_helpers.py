"""Helpers for the M6 assembly acceptance tests. Public surfaces only."""

from __future__ import annotations

import json
import re
import subprocess
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from m5_helpers import (
    TERMINAL,
    art_path,
    artifact,
    base,
    ready,
    shot,
    shots_approved,
    world,
)
from rf_helpers import wait_job

PREVIEW_STEPS = [
    "Preparing shots",
    "Joining video",
    "Placing dialogue",
    "Mixing audio",
    "Measuring loudness",
    "Normalising loudness",
    "Burning captions",
    "Encoding",
]
FINAL_STEPS = PREVIEW_STEPS + ["Verifying", "Writing cover and credits"]
VOICED = ["s1", "s2", "s5"]


class Kill(BaseException):
    """Simulates a killed render."""


@contextmanager
def reel_world(tmp_path, **over):
    """A mock world with all five shots approved (SHOTS_APPROVED); client is open."""
    w = world(tmp_path, **over)
    with w.client:
        pid = ready(w)
        shots_approved(w, pid)
        yield w, pid


@contextmanager
def voiced_world(tmp_path, **over):
    """A mock world that stops at FRAMES_APPROVED."""
    w = world(tmp_path, **over)
    with w.client:
        yield w, ready(w)


def asm_dir(w, pid: str) -> Path:
    from reelforge.db.models import Project

    with w.ctx.session_factory() as s:
        p = s.get(Project, pid)
        assert p is not None
        return Path(w.settings.data_root) / p.data_dir / "assembly"


def get_asm(w, pid: str) -> dict[str, Any]:
    r = w.client.get(f"{base(pid)}/assembly")
    assert r.status_code == 200, r.text
    return r.json()


def build(w, pid: str, **body: Any) -> dict[str, Any]:
    r = w.client.post(f"{base(pid)}/assembly:build", json=body)
    assert r.status_code == 200, r.text
    return r.json()


def get_edl(w, pid: str) -> dict[str, Any]:
    r = w.client.get(f"{base(pid)}/assembly/edl")
    assert r.status_code == 200, r.text
    return r.json()


def edit(w, pid: str, **op: Any):
    return w.client.post(f"{base(pid)}/assembly:edit", json=op)


def edit_ok(w, pid: str, **op: Any) -> dict[str, Any]:
    r = edit(w, pid, **op)
    assert r.status_code == 200, r.text
    return r.json()


def until(pred, timeout: float = 60.0, what: str = "condition"):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        v = pred()
        if v:
            return v
        time.sleep(0.05)
    raise AssertionError(f"{what} not met in time")


def wait_preview(w, pid: str, state: str = "up_to_date", timeout: float = 60.0) -> dict[str, Any]:
    return until(
        lambda: (a := get_asm(w, pid))["preview"]["state"] == state and a,
        timeout,
        f"preview state {state}",
    )


def jobs_of(w, pid: str, type_: str):
    from reelforge.db.models import Job
    from sqlalchemy import select

    with w.ctx.session_factory() as s:
        rows = list(s.scalars(select(Job).where(Job.project_id == pid, Job.type == type_)))
        for r in rows:
            s.expunge(r)
        return rows


def export(w, pid: str, accept: bool = True):
    return w.client.post(f"{base(pid)}/assembly:export", json={"accept_licence_warning": accept})


def export_ok(w, pid: str, timeout: float = 120.0):
    r = export(w, pid)
    assert r.status_code == 202, r.text
    job = wait_job(w.ctx, r.json()["id"], TERMINAL, timeout=timeout)
    assert job.status == "succeeded", job.error
    return job


def take_id(w, pid: str, sid: str) -> str:
    s = shot(w, pid, sid)
    act = [t for t in s["takes"] if t["active"]]
    assert len(act) == 1
    return act[0]["id"]


def voice_take_id(w, pid: str, sid: str) -> str:
    r = w.client.get(f"{base(pid)}/voices")
    line = next(x for x in r.json()["lines"] if x["scene_id"] == sid)
    return next(t["id"] for t in line["takes"] if t["active"])


def probe(path: Path) -> dict[str, Any]:
    res = subprocess.run(
        ["ffprobe", "-v", "error", "-show_streams", "-show_format", "-of", "json", str(path)],
        capture_output=True, text=True, timeout=60, check=True,
    )
    d = json.loads(res.stdout)
    d["video"] = next((s for s in d["streams"] if s["codec_type"] == "video"), None)
    d["audio"] = next((s for s in d["streams"] if s["codec_type"] == "audio"), None)
    return d


def _ffmpeg_err(path: Path, af: str) -> str:
    res = subprocess.run(
        ["ffmpeg", "-nostats", "-hide_banner", "-i", str(path), "-vn", "-af", af, "-f", "null", "-"],
        capture_output=True, text=True, timeout=120,
    )
    return res.stderr


def loudness(path: Path) -> tuple[float, float]:
    """(integrated LUFS, true peak dBTP) from ffmpeg ebur128."""
    err = _ffmpeg_err(path, "ebur128=peak=true")
    summary = err[err.rindex("Summary:"):]
    i = float(re.search(r"I:\s+(-?[\d.]+) LUFS", summary).group(1))  # type: ignore[union-attr]
    p = float(re.search(r"Peak:\s+(-?[\d.]+) dBFS", summary).group(1))  # type: ignore[union-attr]
    return i, p


def max_volume_db(path: Path) -> float:
    err = _ffmpeg_err(path, "volumedetect")
    m = re.search(r"max_volume:\s+(-?[\d.]+|-inf) dB", err)
    assert m, err[-500:]
    return float("-inf") if m.group(1) == "-inf" else float(m.group(1))


def first_sound_s(path: Path) -> float:
    """Time at which the audio first rises above -50 dB."""
    err = _ffmpeg_err(path, "silencedetect=noise=-50dB:d=0.1")
    ends = [float(x) for x in re.findall(r"silence_end:\s+(-?[\d.]+)", err)]
    starts = [float(x) for x in re.findall(r"silence_start:\s+(-?[\d.]+)", err)]
    assert starts and starts[0] <= 0.05, err[-500:]
    assert ends, "audio never rises above -50 dB"
    return ends[0]


def small_edl(edl, n: int = 2):
    keep = {s.scene_id for s in edl.video[:n]}
    return edl.model_copy(
        update={
            "video": edl.video[:n],
            "dialogue": [d for d in edl.dialogue if d.scene_id in keep],
            "captions": [c for c in edl.captions if c.scene_id in keep],
        }
    )


def new_cancel():
    from reelforge.adapters.base import CancelToken

    return CancelToken()


def render(w, edl, out_dir: Path, profile: str = "preview", hooks=None, progress=None):
    from rf_helpers import run_async
    from reelforge.assembly.render import render_edl

    out_dir.mkdir(parents=True, exist_ok=True)
    return run_async(
        render_edl(
            w.ctx, edl, out_dir, profile=profile,  # type: ignore[arg-type]
            progress=progress or (lambda pct, msg: None), cancel=new_cancel(), hooks=hooks,
        )
    )


def kinds(w, pid: str) -> list[str]:
    from rf_helpers import artifacts_of

    return [a.kind for a in artifacts_of(w.ctx, pid)]


__all__ = [n for n in dir() if not n.startswith("_")]
_ = (art_path, artifact)
