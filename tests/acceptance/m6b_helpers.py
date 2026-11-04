"""Helpers for the M6b voice emotion, age and speed acceptance tests. Public surfaces only."""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any

from m4_helpers import (
    LINES,
    action,
    approve_all,
    base,
    cast_approved,
    generate,
    get_voices,
    line_of,
    read_wav,
    set_presets,
    voice_world,
    wav_bytes,
    wrap_worker,
)

__all__ = [
    "LINES", "action", "approve_all", "base", "cast_approved", "generate", "get_voices", "line_of",
    "read_wav", "set_presets", "voice_world", "wav_bytes", "wrap_worker",
]

UNKNOWN_JOY = 'Unknown emotion "joy". Use one of: happy, sad, fear, anger.'
AGE_ERROR = "Age must be a whole number from 1 to 120."

# Our own mapping file. Tests point `emotion_mapping_path` at it, so they never depend on the
# values that ship in the packaged table.
MAPPING = """\
[phrase]
gap_ms = 150

[emotion.happy]
tags = ["[laughter]"]
tag_position = "prefix"
pitch = "high pitch"
duration_scale = 0.9
[emotion.happy.generation]
guidance_scale = 2.5
[emotion.happy.post]
semitones = 0.0
gain_db = 0.0
pause_s = 0.0

[emotion.sad]
tags = ["[sigh]"]
tag_position = "prefix"
pitch = "low pitch"
duration_scale = 1.25
[emotion.sad.generation]
guidance_scale = 2.0
[emotion.sad.post]
semitones = -2.0
gain_db = -3.0
pause_s = 0.0

[emotion.fear]
tags = ["[surprise-ah]"]
tag_position = "prefix"
pitch = "high pitch"
duration_scale = 0.8
[emotion.fear.post]
semitones = 0.0
gain_db = 0.0
pause_s = 0.0

[emotion.anger]
tags = []
tag_position = "prefix"
pitch = "low pitch"
duration_scale = 0.95
[emotion.anger.post]
semitones = 0.0
gain_db = 0.0
pause_s = 0.0
"""


def write_mapping(tmp_path: Path, text: str = MAPPING) -> Path:
    p = tmp_path / "my_emotions.toml"
    p.write_text(text)
    return p


def emo_world(tmp_path, mapping: str = MAPPING, **over):
    path = write_mapping(tmp_path, mapping)
    ctx, client = voice_world(tmp_path, emotion_mapping_path=path, **over)
    return ctx, client, path


def rows_of(log: Path) -> list[dict[str, Any]]:
    """Every worker batch row seen so far, in order (needs `wrap_worker`)."""
    if not log.exists():
        return []
    out: list[dict[str, Any]] = []
    for call in log.read_text().splitlines():
        for ln in json.loads(call)["batch"].splitlines():
            if ln.strip():
                out.append(json.loads(ln))
    return out


def rows_for(log: Path, scene_id: str) -> list[dict[str, Any]]:
    return [r for r in rows_of(log) if r["id"] == scene_id or r["id"].startswith(scene_id + "#")]


def take_rows(ctx, pid: str, scene_id: str):
    from reelforge.db.models import Artifact
    from sqlalchemy import select

    with ctx.session_factory() as s:
        rows = list(
            s.scalars(
                select(Artifact)
                .where(
                    Artifact.project_id == pid,
                    Artifact.kind == "voice_take",
                    Artifact.owner_id == scene_id,
                )
                .order_by(Artifact.take_no)
            )
        )
        for r in rows:
            s.expunge(r)
        return rows


def inputs_of(ctx, artifact_id: str) -> list[str]:
    from reelforge.db.models import ArtifactInput
    from sqlalchemy import select

    with ctx.session_factory() as s:
        return list(
            s.scalars(select(ArtifactInput.input_artifact_id).where(ArtifactInput.artifact_id == artifact_id))
        )


def gen_lines(client, ctx, pid: str, *ids: str):
    _, job = generate(client, ctx, pid, mode="lines", lines=list(ids))
    assert job.status == "succeeded", job.error
    return job


def active_take(client, pid: str, scene_id: str) -> dict[str, Any]:
    ln = line_of(client, pid, scene_id)
    act = [t for t in ln["takes"] if t["active"]]
    assert len(act) == 1, ln["takes"]
    return act[0]


def set_emotion(client, pid: str, scene_id: str, emotion: str | None):
    return action(client, pid, scene_id, "set-emotion", emotion=emotion)


def project_with_presets(client, ctx) -> str:
    pid = cast_approved(client, ctx)
    set_presets(client, pid)
    return pid


def set_age(client, pid: str, key: str, age: Any):
    return client.post(f"{base(pid)}/cast/{key}:set-age", json={"age": age})


# audio measurement --------------------------------------------------------------


def tone_freq(samples: list[int], rate: int) -> float:
    """Frequency of a clean tone from zero crossings over the loud middle part."""
    n = len(samples)
    mid = samples[n // 5 : n - n // 5]
    cross = sum(1 for a, b in zip(mid, mid[1:], strict=False) if (a < 0) != (b < 0))
    return cross / 2 / (len(mid) / rate)


def rms(samples: list[int]) -> float:
    return math.sqrt(sum(x * x for x in samples) / max(1, len(samples)))


def interior_silence_runs(samples: list[int], rate: int, thresh: int = 150) -> list[float]:
    """Lengths (s) of silent runs strictly between the first and last loud samples."""
    loud = [i for i, x in enumerate(samples) if abs(x) > thresh]
    if not loud:
        return []
    runs: list[float] = []
    start: int | None = None
    for i in range(loud[0], loud[-1] + 1):
        if abs(samples[i]) <= thresh:
            if start is None:
                start = i
        elif start is not None:
            runs.append((i - start) / rate)
            start = None
    return runs


def longest_gap_s(path_or_bytes) -> float:
    s, rate, _, _ = read_wav(path_or_bytes)
    runs = interior_silence_runs(s, rate)
    return max(runs) if runs else 0.0
