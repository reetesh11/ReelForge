"""The resumable render engine: ten named steps, the first eight live here."""

from __future__ import annotations

import json
import re
import shutil
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal

from reelforge.adapters.base import AdapterError, CancelToken
from reelforge.assembly import filtergraph as fg
from reelforge.assembly.edl import FPS, Edl, edl_hash
from reelforge.assembly.ffmpeg import filter_script_args, run_ffmpeg
from reelforge.assembly.render_state import (
    RenderHooks,
    RenderState,
    commit_part,
    part_path,
)
from reelforge.assembly.state import StepError
from reelforge.db.models import Artifact

if TYPE_CHECKING:
    from reelforge.context import AppContext

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
FINAL_STEPS = [*PREVIEW_STEPS, "Verifying", "Writing cover and credits"]

PREPARING, JOINING, DIALOGUE, MIXING, MEASURING, NORMALISING, CAPTIONS, ENCODING = PREVIEW_STEPS

RenderProgress = Callable[[float, str], None]

_INTERMEDIATE = [
    "-c:v",
    "libx264",
    "-preset",
    "ultrafast",
    "-crf",
    "12",
    "-pix_fmt",
    "yuv420p",
    "-r",
    str(FPS),
]


@dataclass
class RenderResult:
    output: Path
    filtergraph: Path
    captions_burned: bool
    step_runs: dict[str, int]


def _artifact_path(ctx: AppContext, artifact_id: str) -> Path | None:
    with ctx.session_factory() as s:
        art = s.get(Artifact, artifact_id)
    if art is None:
        return None
    path = ctx.store.absolute_path(art)
    return path if path.is_file() else None


def _write_script(path: Path, graph: fg.FilterGraph) -> Path:
    path.write_text(graph.to_script(), encoding="utf-8")
    return path


class _Render:
    def __init__(
        self,
        ctx: AppContext,
        edl: Edl,
        out_dir: Path,
        profile: fg.Profile,
        cancel: CancelToken,
        state: RenderState,
    ) -> None:
        self.ctx = ctx
        self.edl = edl
        self.dir = out_dir
        self.profile = profile
        self.cancel = cancel
        self.state = state
        self.prep_dir = out_dir / "prep"
        self.joined = out_dir / "joined.mp4"
        self.dialogue = out_dir / "dialogue.wav"
        self.mix = out_dir / "mix.wav"
        self.loudness = out_dir / "loudness.json"
        self.normalised = out_dir / "normalised.wav"
        self.ass = out_dir / "captions.ass"
        stem = profile.out_name.removesuffix(".mp4")
        self.output = out_dir / profile.out_name
        self.script = out_dir / f"{stem}.filtergraph.txt"

    def prep_files(self) -> list[Path]:
        return [self.prep_dir / f"shot_{i:03d}.mp4" for i in range(len(self.edl.video))]

    async def ffmpeg(self, step: str, *tail: str, stderr: bool = False) -> str:
        res = await run_ffmpeg(
            self.ctx, ["-loglevel", "info" if stderr else "error", *tail], self.cancel, step=step
        )
        return res.stderr

    # steps -------------------------------------------------------------------------------

    async def prepare(self) -> None:
        if not self.edl.video:
            raise StepError(PREPARING, "The reel has no shots.")
        sources: list[Path] = []
        for shot in self.edl.video:
            path = _artifact_path(self.ctx, shot.artifact)
            if path is None:
                raise StepError(PREPARING, f"A shot file is missing: {shot.scene_id}")
            sources.append(path)
        self.prep_dir.mkdir(parents=True, exist_ok=True)
        for i, (shot, src, dst) in enumerate(
            zip(self.edl.video, sources, self.prep_files(), strict=True)
        ):
            if dst.exists():
                continue
            script = _write_script(
                self.prep_dir / f"shot_{i:03d}.fg",
                fg.build_normalise_graph(shot, self.profile.width, self.profile.height),
            )
            await self.ffmpeg(
                PREPARING,
                "-i",
                str(src),
                *filter_script_args(script),
                "-map",
                "[v]",
                "-an",
                *_INTERMEDIATE,
                "-frames:v",
                str(shot.frames),
                "-f",
                "mp4",
                str(part_path(dst)),
            )
            commit_part(dst)

    async def join(self) -> None:
        script = _write_script(self.dir / "join.fg", fg.build_join_graph(self.edl))
        inputs: list[str] = []
        for f in self.prep_files():
            inputs += ["-i", str(f)]
        await self.ffmpeg(
            JOINING,
            *inputs,
            *filter_script_args(script),
            "-map",
            "[v]",
            "-an",
            *_INTERMEDIATE,
            "-frames:v",
            str(self.edl.total_frames),
            "-f",
            "mp4",
            str(part_path(self.joined)),
        )
        commit_part(self.joined)

    async def place_dialogue(self) -> None:
        inputs: list[str] = []
        for clip in self.edl.dialogue:
            path = _artifact_path(self.ctx, clip.artifact)
            if path is None:
                raise StepError(DIALOGUE, f"A voice file is missing: {clip.scene_id}")
            inputs += ["-i", str(path)]
        script = _write_script(self.dir / "dialogue.fg", fg.build_dialogue_graph(self.edl))
        await self.ffmpeg(
            DIALOGUE,
            *inputs,
            *filter_script_args(script),
            "-map",
            "[dlg]",
            "-c:a",
            "pcm_f32le",
            "-f",
            "wav",
            str(part_path(self.dialogue)),
        )
        commit_part(self.dialogue)

    async def mix_audio(self) -> None:
        cue_inputs: list[str] = []
        for cue in self.edl.audio:
            if cue.artifact is None or cue.kind == "silence":
                continue
            path = _artifact_path(self.ctx, cue.artifact)
            if path is None:
                raise StepError(MIXING, f"A sound file is missing: {cue.cue_id}")
            cue_inputs += ["-i", str(path)]
        script = _write_script(self.dir / "mix.fg", fg.build_mix_graph(self.edl))
        await self.ffmpeg(
            MIXING,
            "-i",
            str(self.dialogue),
            *cue_inputs,
            *filter_script_args(script),
            "-map",
            "[mix]",
            "-c:a",
            "pcm_f32le",
            "-f",
            "wav",
            str(part_path(self.mix)),
        )
        commit_part(self.mix)

    async def measure(self) -> None:
        script = _write_script(self.dir / "loudnorm1.fg", fg.build_loudnorm_graph())
        err = await self.ffmpeg(
            MEASURING,
            "-i",
            str(self.mix),
            *filter_script_args(script),
            "-map",
            "[n]",
            "-f",
            "null",
            "-",
            stderr=True,
        )
        blocks = re.findall(r"\{[^{}]*\}", err, flags=re.S)
        data: dict[str, Any] = {"silent": True}
        for block in reversed(blocks):
            try:
                raw: dict[str, Any] = json.loads(block)
                values = fg.to_loudnorm_values(raw)
            except (ValueError, KeyError):
                continue
            silent = any(v in ("-inf", "inf", "nan") for v in values.values())
            data = {"silent": silent, **values}
            break
        tmp = part_path(self.loudness)
        tmp.write_text(json.dumps(data), encoding="utf-8")
        commit_part(self.loudness)

    async def normalise(self) -> None:
        data: dict[str, Any] = json.loads(self.loudness.read_text(encoding="utf-8"))
        if data.get("silent"):
            shutil.copyfile(self.mix, part_path(self.normalised))
            commit_part(self.normalised)
            return
        measured = {k: str(v) for k, v in data.items() if k != "silent"}
        script = _write_script(self.dir / "loudnorm2.fg", fg.build_loudnorm_graph(measured))
        await self.ffmpeg(
            NORMALISING,
            "-i",
            str(self.mix),
            *filter_script_args(script),
            "-map",
            "[n]",
            "-c:a",
            "pcm_f32le",
            "-f",
            "wav",
            str(part_path(self.normalised)),
        )
        commit_part(self.normalised)

    async def captions(self) -> None:
        from reelforge.assembly.caption_step import prepare_captions  # noqa: PLC0415

        burn = await prepare_captions(self.ctx, self.edl, self.dir, self.ass)
        self.state.meta["captions_burned"] = burn

    async def encode(self) -> None:
        burn = bool(self.state.meta.get("captions_burned"))
        fonts = str(self.ctx.settings.devanagari_font.parent) if burn else None
        graph = fg.build_encode_graph(self.profile, str(self.ass) if burn else None, fonts)
        script = _write_script(self.script, graph)
        p = self.profile
        codec = ["-c:v", "libx264", "-preset", p.preset, "-crf", str(p.crf)]
        if p.profile_v:
            codec += ["-profile:v", p.profile_v]
        await self.ffmpeg(
            ENCODING,
            "-i",
            str(self.joined),
            "-i",
            str(self.normalised),
            *filter_script_args(script),
            "-map",
            "[v]",
            "-map",
            "[a]",
            *codec,
            "-pix_fmt",
            "yuv420p",
            "-r",
            str(FPS),
            "-frames:v",
            str(self.edl.total_frames),
            "-c:a",
            "aac",
            "-b:a",
            p.audio_bitrate,
            "-ar",
            str(fg.SAMPLE_RATE),
            "-ac",
            "2",
            "-t",
            f"{self.edl.total_duration_s:.6f}",
            "-movflags",
            "+faststart",
            "-f",
            "mp4",
            str(part_path(self.output)),
        )
        commit_part(self.output)


async def render_edl(
    ctx: AppContext,
    edl: Edl,
    out_dir: Path,
    *,
    profile: Literal["preview", "final"],
    progress: RenderProgress,
    cancel: CancelToken,
    hooks: RenderHooks | None = None,
    step_total: int | None = None,
) -> RenderResult:
    """Run the eight render steps, resuming from `out_dir/state.json` when it matches."""
    prof = fg.PROFILES[profile]
    out_dir.mkdir(parents=True, exist_ok=True)
    state = RenderState.open(out_dir, edl_hash(edl), profile)
    r = _Render(ctx, edl, out_dir, prof, cancel, state)
    plan: list[tuple[str, list[Path], Callable[[], Awaitable[None]]]] = [
        (PREPARING, r.prep_files(), r.prepare),
        (JOINING, [r.joined], r.join),
        (DIALOGUE, [r.dialogue], r.place_dialogue),
        (MIXING, [r.mix], r.mix_audio),
        (MEASURING, [r.loudness], r.measure),
        (NORMALISING, [r.normalised], r.normalise),
        (CAPTIONS, [r.ass], r.captions),
        (ENCODING, [r.output, r.script], r.encode),
    ]
    total = step_total or len(plan)
    for i, (name, outputs, fn) in enumerate(plan, start=1):
        if cancel.cancelled:
            raise AdapterError("cancelled")
        progress((i - 1) / total * 100, f"{name} ({i} of {total})")
        await state.run_step(name, outputs, fn, hooks)
    return RenderResult(
        output=r.output,
        filtergraph=r.script,
        captions_burned=bool(state.meta.get("captions_burned")),
        step_runs={name: state.runs(name) for name, _, _ in plan},
    )
