"""Helpers for the M6c music, sound effects, ambience and silence acceptance tests.

Public surfaces only. Mix tests build an `Edl` by hand and run the graph from
`build_mix_graph` through ffmpeg with known tones, so levels and timing are exact.
"""

from __future__ import annotations

import json
import math
import subprocess
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from m4_helpers import read_wav, wav_bytes, wav_seconds
from m5_helpers import base, world
from m5_helpers import frames_approved as _frames_approved
from m5_helpers import shots_approved as _shots_approved
from m5_helpers import story_text as _reel_story_text
from m5_helpers import voices_approved as _voices_approved
from m6_helpers import until
from rf_helpers import create_project, make_client, make_ctx, make_settings, wait_job
from story_helpers import put, story_dict

TERMINAL = {"succeeded", "failed", "cancelled"}
FREQ = {"music": 220.0, "sfx": 880.0, "ambience": 330.0}
DIALOGUE_HZ = 1000.0


# cue and story builders ------------------------------------------------------------------


def at(scene: str, offset: float = 0.0, at_: str = "scene_start") -> dict[str, Any]:
    d: dict[str, Any] = {"scene": scene, "offset": offset}
    if at_ != "scene_start":
        d["at"] = at_
    return d


def cue(id_: str, kind: str, start: dict[str, Any], **kw: Any) -> dict[str, Any]:
    d: dict[str, Any] = {"id": id_, "kind": kind, "start": start}
    if kind != "silence":
        d.setdefault("prompt", f"{kind} for {id_}")
        d.setdefault("source", "generate")
    d.update(kw)
    return d


def story_with_audio(audio: list[dict[str, Any]] | None, n: int = 5, **over: Any) -> str:
    """Five two-second scenes: s1 0-2, s2 2-4, s3 4-6, s4 6-8, s5 8-10."""
    extra = dict(over)
    if audio is not None:
        extra["audio"] = audio
    return json.dumps(story_dict(n, **extra), ensure_ascii=False)


# a story with every kind of cue; times resolve on the five two-second scenes
STD_CUES: list[dict[str, Any]] = [
    cue("m1", "music", at("s1"), duration=3.0, prompt="festive shehnai and dholak", duck=True),
    cue("fx1", "sfx", at("s2", 0.5), duration=1.2, prompt="gong slam"),
    cue("sil1", "silence", at("s4"), duration=1.0),
    cue("f1", "music", at("s3"), duration=2.0, source="file", prompt="my own track"),
    cue("amb1", "ambience", at("s1"), end=at("s5", at_="scene_end"), prompt="wedding crowd murmur"),
]


@contextmanager
def light_world(
    tmp_path, audio: list[dict[str, Any]] | None = None, text: str | None = None, adapter=None, **over
):
    """Mock world with a saved (not approved) story; yields (ctx, client, pid).

    `adapter` is an optional factory taking the settings and returning the adapter to use.
    """
    settings = make_settings(tmp_path, **over)
    ctx = make_ctx(settings, available_gb=64.0, adapter=adapter(settings) if adapter else None)
    client = make_client(ctx)
    with client:
        pid = create_project(client, "Sound tale")["id"]
        r = put(client, pid, text if text is not None else story_with_audio(audio))
        assert r.status_code == 200, r.text
        yield ctx, client, pid


def audio_url(pid: str, tail: str = "") -> str:
    return f"{base(pid)}/audio{tail}"


def get_audio(client, pid: str) -> dict[str, Any]:
    r = client.get(audio_url(pid))
    assert r.status_code == 200, r.text
    return r.json()


def cue_out(client, pid: str, cue_id: str) -> dict[str, Any]:
    return next(c for c in get_audio(client, pid)["cues"] if c["id"] == cue_id)


def generate_cue(client, ctx, pid: str, cue_id: str, timeout: float = 60.0):
    r = client.post(audio_url(pid, f"/cues/{cue_id}:generate"))
    assert r.status_code == 202, r.text
    return r.json(), wait_job(ctx, r.json()["id"], TERMINAL, timeout=timeout)


def generated(client, ctx, pid: str, cue_id: str):
    body, job = generate_cue(client, ctx, pid, cue_id)
    assert job.status == "succeeded", job.error
    return body, job


def put_cue(client, pid: str, body: dict[str, Any]):
    return client.put(audio_url(pid, f"/cues/{body['id']}"), json=body)


def take_artifacts(ctx, pid: str, cue_id: str | None = None):
    from reelforge.db.models import Artifact
    from sqlalchemy import select

    with ctx.session_factory() as s:
        rows = list(
            s.scalars(
                select(Artifact)
                .where(Artifact.project_id == pid, Artifact.kind == "audio_take")
                .order_by(Artifact.take_no)
            )
        )
        rows = [r for r in rows if cue_id is None or r.owner_id == cue_id]
        for r in rows:
            s.expunge(r)
        return rows


def take_path(ctx, art) -> Path:
    return Path(ctx.store.absolute_path(art))


def stale_items(client, pid: str) -> list[dict[str, Any]]:
    r = client.get(f"{base(pid)}/stale")
    assert r.status_code == 200, r.text
    return r.json()["items"]


def stale_audio(client, pid: str) -> set[tuple[str, str]]:
    return {
        (i["owner_id"], i["kind"]) for i in stale_items(client, pid) if i["owner_type"] == "audio_cue"
    }


def jobs_of_type(ctx, pid: str, type_: str):
    from reelforge.db.models import Job
    from sqlalchemy import select

    with ctx.session_factory() as s:
        rows = list(s.scalars(select(Job).where(Job.project_id == pid, Job.type == type_)))
        for r in rows:
            s.expunge(r)
        return rows


def upload_cue_file(client, pid: str, cue_id: str, data: bytes, name: str = "clip.wav", note=None):
    form = {"licence_note": note} if note is not None else {}
    return client.post(
        audio_url(pid, f"/cues/{cue_id}:upload"),
        files={"file": (name, data, "application/octet-stream")},
        data=form,
    )


# reel world with cues in the approved story ---------------------------------------------


def reel_text_with_audio(audio: list[dict[str, Any]]) -> str:
    d = json.loads(_reel_story_text())
    d["audio"] = audio
    return json.dumps(d, ensure_ascii=False)


@contextmanager
def audio_reel_world(tmp_path, audio: list[dict[str, Any]], **over):
    """Like `reel_world`, but the approved story already carries `audio`; stage SHOTS_APPROVED."""
    w = world(tmp_path, **over)
    with w.client:
        pid = _voices_approved(w, reel_text_with_audio(audio))
        _frames_approved(w, pid)
        _shots_approved(w, pid)
        yield w, pid


# ffmpeg tone and mix measurement -----------------------------------------------------------


def _ff(argv: list[str]) -> None:
    res = subprocess.run(
        ["ffmpeg", "-nostdin", "-y", "-loglevel", "error", *argv],
        capture_output=True, text=True, timeout=120,
    )
    assert res.returncode == 0, res.stderr[-800:]


def tone_file(path: Path, freq: float, seconds: float) -> Path:
    """48 kHz stereo WAV tone at 0.5 amplitude."""
    _ff([
        "-f", "lavfi", "-i", f"sine=frequency={freq}:sample_rate=48000:duration={seconds}",
        "-af", "volume=4,aformat=channel_layouts=stereo", "-c:a", "pcm_s16le", str(path),
    ])
    return path


def dialogue_file(path: Path, total: float, start: float, seconds: float) -> Path:
    """A reel-length dialogue bed: a 1 kHz tone from `start` for `seconds`, silence elsewhere."""
    ms = int(start * 1000)
    _ff([
        "-f", "lavfi", "-i", f"sine=frequency={DIALOGUE_HZ}:sample_rate=48000:duration={seconds}",
        "-af", f"volume=4,aformat=channel_layouts=stereo,adelay={ms}|{ms},apad=whole_dur={total}",
        "-c:a", "pcm_s16le", str(path),
    ])
    return path


def make_edl(total: float, audio: list[Any], dialogue: tuple[float, float] | None = None, mix=None):
    from reelforge.assembly.edl import Edl, EdlDialogue, EdlShot

    dlg = []
    if dialogue is not None:
        dlg = [EdlDialogue(scene_id="s1", artifact="dlg", offset_s=dialogue[0], duration_s=dialogue[1])]
    extra: dict[str, Any] = {"audio": audio}
    if mix is not None:
        extra["mix"] = mix
    return Edl(
        project_id="p",
        video=[EdlShot(scene_id="s1", artifact="vid", source_duration_s=total, in_s=0.0, out_s=total)],
        dialogue=dlg,
        captions=[],
        **extra,
    )


def edl_cue(id_: str, kind: str, start: float, end: float, *, gain=0.0, fade_in=0.0, fade_out=0.0,
            duck=False, artifact: str | None = "x"):
    from reelforge.assembly.edl import EdlAudio

    return EdlAudio(
        cue_id=id_, kind=kind, artifact=None if kind == "silence" else artifact,  # type: ignore[arg-type]
        start_s=start, end_s=end, gain_db=gain, fade_in_s=fade_in, fade_out_s=fade_out, duck=duck,
    )


def run_mix(tmp_path: Path, edl, dialogue: Path, files: list[Path], name: str = "mix") -> list[int]:
    """Run `build_mix_graph(edl)` through ffmpeg and return the left channel as 16-bit samples."""
    from reelforge.assembly.ffmpeg import filter_script_args
    from reelforge.assembly.filtergraph import build_mix_graph

    script = tmp_path / f"{name}.fg"
    script.write_text(build_mix_graph(edl).to_script())
    out = tmp_path / f"{name}.mix.wav"
    argv = ["-i", str(dialogue)]
    for f in files:
        argv += ["-i", str(f)]
    argv += [*filter_script_args(script), "-map", "[mix]", "-c:a", "pcm_s16le",
             "-ar", "48000", "-ac", "2", str(out)]
    _ff(argv)
    samples, rate, ch, _ = read_wav(out)
    assert rate == 48000 and ch == 2
    return samples[0::2]


def goertzel_db(samples: list[int], freq: float, t0: float, t1: float, rate: int = 48000) -> float:
    """Level (dBFS of a sine's peak) of `freq` in the window [t0, t1) seconds."""
    seg = samples[int(t0 * rate) : int(t1 * rate)]
    n = len(seg)
    if n == 0:
        return -200.0
    w = 2 * math.pi * freq / rate
    coeff = 2 * math.cos(w)
    s1 = s2 = 0.0
    for x in seg:
        s0 = x / 32768.0 + coeff * s1 - s2
        s2, s1 = s1, s0
    power = s1 * s1 + s2 * s2 - coeff * s1 * s2
    amp = 2 * math.sqrt(max(power, 0.0)) / n
    return 20 * math.log10(amp) if amp > 1e-9 else -200.0


def onset_s(samples: list[int], freq: float, around: float, span: float = 0.3) -> float:
    """First time near `around` where `freq` reaches half its steady amplitude (10 ms windows)."""
    steady = goertzel_db(samples, freq, around + 0.4, around + 0.8)
    t = max(0.0, around - span)
    while t < around + span:
        if goertzel_db(samples, freq, t, t + 0.01) >= steady - 6.0:
            return t + 0.005
        t += 0.005
    raise AssertionError(f"no onset of {freq} Hz near {around}")


def duration_of(samples: list[int], rate: int = 48000) -> float:
    return len(samples) / rate


_ = (wav_bytes, wav_seconds, until)
