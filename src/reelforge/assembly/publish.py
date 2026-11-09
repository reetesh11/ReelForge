"""Credits and licence checks for an exported reel, and writing the versioned folder."""

from __future__ import annotations

import json
import shutil
import threading
from pathlib import Path
from typing import TYPE_CHECKING, Any

from sqlalchemy import func, select

from reelforge.adapters.base import CancelToken
from reelforge.assembly import ffmpeg
from reelforge.assembly.align import ALIGN_MODEL_KEY, MlxWhisperAligner
from reelforge.assembly.build import assembly_dir
from reelforge.assembly.edl import FPS, HEIGHT, WIDTH, Edl
from reelforge.assembly.state import StepError
from reelforge.cast.licence import is_non_commercial
from reelforge.db.models import Artifact, ArtifactInput, Project, ReelVersion, utcnow

if TYPE_CHECKING:
    from reelforge.context import AppContext


def _model_keys(ctx: AppContext, edl: Edl) -> set[str]:
    """Model keys of the shot and voice takes and of everything they were made from."""
    pending = list(
        dict.fromkeys([*(s.artifact for s in edl.video), *(d.artifact for d in edl.dialogue)])
    )
    seen: set[str] = set()
    keys: set[str] = set()
    with ctx.session_factory() as s:
        while pending:
            aid = pending.pop()
            if aid in seen:
                continue
            seen.add(aid)
            art = s.get(Artifact, aid)
            if art is None:
                continue
            keys.add(art.model_key)
            pending.extend(
                s.scalars(
                    select(ArtifactInput.input_artifact_id).where(ArtifactInput.artifact_id == aid)
                )
            )
    return keys


def _audio_credits(ctx: AppContext, edl: Edl) -> list[dict[str, Any]]:
    """One entry per cue that has a take: model and licence, or the owner's file and note."""
    out: list[dict[str, Any]] = []
    if not any(cue.artifact for cue in edl.audio):
        return out
    with ctx.session_factory() as s:
        for cue in edl.audio:
            take = s.get(Artifact, cue.artifact) if cue.artifact else None
            if take is None:
                continue
            params: dict[str, Any] = take.params or {}
            if take.model_key == "upload":
                out.append(
                    {
                        "cue_id": cue.cue_id,
                        "kind": cue.kind,
                        "file_name": str(params.get("file_name") or ""),
                        "licence": str(params.get("licence_note") or "").strip(),
                    }
                )
                continue
            try:
                entry = ctx.registry.get(take.model_key)
                model, version, licence = entry.id, entry.revision, entry.license
            except KeyError:
                model, version, licence = str(params.get("model_id") or take.model_key), "", ""
            out.append(
                {
                    "cue_id": cue.cue_id,
                    "kind": cue.kind,
                    "model": model,
                    "version": version,
                    "licence": licence,
                }
            )
    return out


def collect_credits(ctx: AppContext, project_id: str, edl: Edl) -> list[dict[str, Any]]:
    """One `{model, version, licence}` per distinct model used by the reel, then one per cue."""
    del project_id
    keys = _model_keys(ctx, edl)
    if isinstance(ctx.aligner, MlxWhisperAligner) and any(c.text.strip() for c in edl.captions):
        keys.add(ALIGN_MODEL_KEY)
    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    for entry in ctx.registry.entries():
        if entry.key not in keys or entry.id in seen:
            continue
        seen.add(entry.id)
        out.append({"model": entry.id, "version": entry.revision, "licence": entry.license})
    return [*out, *_audio_credits(ctx, edl)]


def licence_warnings(credits: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """The credits whose licence is empty or non-commercial; an upload only needs a note."""
    out: list[dict[str, Any]] = []
    for c in credits:
        text = str(c.get("licence", ""))
        own_file = "cue_id" in c and "model" not in c
        if (not text.strip()) if own_file else is_non_commercial(text):
            out.append(c)
    return out


VERIFYING = "Verifying"
WRITING = "Writing cover and credits"
DURATION_TOLERANCE_S = 0.1
_publish_lock = threading.Lock()


def verify_output(path: Path, edl: Edl) -> None:
    """Check the exported file with ffprobe; raises StepError naming the failing check."""

    def fail(check: str) -> StepError:
        return StepError(VERIFYING, f"Verification failed: {check}.")

    try:
        info = ffmpeg.probe(path)
    except (ValueError, OSError):
        raise fail("the file cannot be read") from None
    video = ffmpeg.stream(info, "video")
    audio = ffmpeg.stream(info, "audio")
    if video is None:
        raise fail("no video stream")
    if (video.get("width"), video.get("height")) != (WIDTH, HEIGHT):
        raise fail("size is not 1080x1920")
    num, _, den = str(video.get("avg_frame_rate", "0/1")).partition("/")
    try:
        rate = float(num) / float(den or 1)
    except (ValueError, ZeroDivisionError):
        rate = 0.0
    if abs(rate - FPS) > 0.01:
        raise fail("frame rate is not 24 fps")
    if audio is None:
        raise fail("no audio stream")
    if int(audio.get("sample_rate", 0)) != 48000 or int(audio.get("channels", 0)) != 2:
        raise fail("audio is not 48 kHz stereo")
    try:
        length = float(info.get("format", {}).get("duration", 0.0))
    except (TypeError, ValueError):
        length = 0.0
    if abs(length - edl.total_duration_s) > DURATION_TOLERANCE_S:
        raise fail("length does not match the edit")


async def extract_cover(
    ctx: AppContext, video: Path, out: Path, cancel: CancelToken, edl: Edl
) -> None:
    """A JPEG frame (1080x1920) from the exported reel."""
    at = min(1.0, edl.total_duration_s / 2)
    part = out.with_name(out.name + ".part")
    await ffmpeg.run_ffmpeg(
        ctx,
        ["-loglevel", "error", "-ss", f"{at:.3f}", "-i", str(video), "-frames:v", "1",
         "-q:v", "2", "-f", "image2", str(part)],
        cancel,
        step=WRITING,
    )  # fmt: skip
    part.replace(out)


def _drop_orphan(ctx: AppContext, project_id: str, folder: Path) -> None:
    """Remove a version folder (and its artifact rows) that never got a `reel_versions` row."""
    if not folder.exists():
        return
    rel = folder.resolve().relative_to(ctx.settings.data_root.resolve()).as_posix()
    with ctx.session_factory.begin() as s:
        for art in s.scalars(
            select(Artifact).where(
                Artifact.project_id == project_id, Artifact.path.startswith(rel + "/")
            )
        ):
            s.delete(art)
    shutil.rmtree(folder, ignore_errors=True)


def published_by(ctx: AppContext, project_id: str, job_id: str) -> ReelVersion | None:
    """The version a given export job already wrote, if any."""
    with ctx.session_factory() as s:
        return s.scalars(
            select(ReelVersion)
            .join(Artifact, Artifact.id == ReelVersion.final_artifact_id)
            .where(ReelVersion.project_id == project_id, Artifact.created_by_job == job_id)
        ).first()


def publish_version(
    ctx: AppContext,
    project_id: str,
    *,
    edl: Edl,
    work_dir: Path,
    final: Path,
    filtergraph: Path,
    cover: Path,
    credits: list[dict[str, Any]],
    job_id: str,
) -> ReelVersion:
    """Write `vNNN/` through a `.part` folder, then the version row, artifacts and stage."""
    from reelforge.assembly.jobs import register_file  # noqa: PLC0415

    done = published_by(ctx, project_id, job_id)
    if done is not None:
        return done
    asm = assembly_dir(ctx, project_id)
    with _publish_lock:
        with ctx.session_factory() as s:
            latest = s.scalar(
                select(func.max(ReelVersion.version)).where(ReelVersion.project_id == project_id)
            )
        version = int(latest or 0) + 1
        target = asm / f"v{version:03d}"
        staging = asm / f".v{version:03d}.part"
        shutil.rmtree(staging, ignore_errors=True)
        _drop_orphan(ctx, project_id, target)
        staging.mkdir(parents=True)
        shutil.copy2(final, staging / "final.mp4")
        shutil.copy2(filtergraph, staging / "final.filtergraph.txt")
        shutil.copy2(cover, staging / "cover.jpg")
        (staging / "credits.json").write_text(
            json.dumps(credits, indent=2, ensure_ascii=False), encoding="utf-8"
        )
        # same shape as the working file (audio and mix always present)
        (staging / "edl.json").write_text(
            json.dumps(edl.model_dump(mode="json"), indent=2, ensure_ascii=False), encoding="utf-8"
        )
        ass = work_dir / "captions.ass"
        if ass.is_file():
            shutil.copy2(ass, staging / "captions.ass")
        staging.replace(target)
        params = {"version": version}
        reel = register_file(
            ctx, project_id, "final", target / "final.mp4", job_id=job_id, inputs=[],
            params=params, duration_s=edl.total_duration_s, width=WIDTH, height=HEIGHT,
        )  # fmt: skip
        register_file(ctx, project_id, "filtergraph", target / "final.filtergraph.txt",
                      job_id=job_id, inputs=[], params=params)  # fmt: skip
        register_file(ctx, project_id, "cover", target / "cover.jpg", job_id=job_id,
                      inputs=[], params=params, width=WIDTH, height=HEIGHT)  # fmt: skip
        register_file(ctx, project_id, "credits", target / "credits.json", job_id=job_id,
                      inputs=[], params=params)  # fmt: skip
        edl_art = register_file(ctx, project_id, "edl", target / "edl.json", job_id=job_id,
                                inputs=[], params=params)  # fmt: skip
        with ctx.session_factory.begin() as s:
            row = ReelVersion(
                project_id=project_id,
                version=version,
                edl_artifact_id=edl_art.id,
                final_artifact_id=reel.id,
                credits=credits,
            )
            s.add(row)
            project = s.get(Project, project_id)
            moved = project is not None and project.stage == "SHOTS_APPROVED"
            if moved and project is not None:
                project.stage = "REEL_EXPORTED"
                project.updated_at = utcnow()
            s.flush()
            s.expunge(row)
    if moved:
        ctx.bus.publish("stage.changed", {"project_id": project_id, "stage": "REEL_EXPORTED"})
    return row
