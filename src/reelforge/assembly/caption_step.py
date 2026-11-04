"""The "Burning captions" step: align, build `captions.ass`, decide whether to burn."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import TYPE_CHECKING, Any

from reelforge.assembly import ffmpeg
from reelforge.assembly.align import AlignmentError, aligner_id
from reelforge.assembly.build import assembly_dir
from reelforge.assembly.captions import WordTiming, build_ass, has_devanagari, resolve_style
from reelforge.assembly.edl import Edl, EdlCaption
from reelforge.assembly.render_state import commit_part, part_path
from reelforge.assembly.state import AssemblyError, StepError
from reelforge.db.models import Artifact

if TYPE_CHECKING:
    from reelforge.context import AppContext

STEP = "Burning captions"
LANGUAGES = {"hindi": "hi", "hinglish": "hi", "english": "en"}


def cache_dir(ctx: AppContext, edl: Edl, out_dir: Path) -> Path:
    try:
        return assembly_dir(ctx, edl.project_id) / "align"
    except AssemblyError:
        return out_dir / "align"


def cache_key(ctx: AppContext, take: Artifact, text: str) -> str:
    raw = f"{take.sha256}\0{text}\0{aligner_id(ctx.aligner)}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def read_cache(path: Path) -> list[WordTiming] | None:
    """Cached words; an empty list for a recorded failure; None when nothing is cached."""
    try:
        data: Any = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if isinstance(data, dict):
        return []
    try:
        return [WordTiming(str(w["text"]), float(w["start_s"]), float(w["end_s"])) for w in data]
    except (KeyError, TypeError, ValueError):
        return None


def write_cache(path: Path, words: list[WordTiming] | None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    body: Any = (
        {"failed": True}
        if words is None
        else [{"text": w.text, "start_s": w.start_s, "end_s": w.end_s} for w in words]
    )
    tmp = path.with_name(path.name + ".part")
    tmp.write_text(json.dumps(body, ensure_ascii=False), encoding="utf-8")
    tmp.replace(path)


def fit_words(text: str, words: list[WordTiming]) -> list[WordTiming]:
    """Show the caption's own words with the aligned timing.

    The aligner hears the voice take, the caption may have been edited: when the word counts
    match the timings are used as they are, otherwise the span is shared by character count.
    """
    tokens = text.split()
    if not tokens or not words:
        return []
    if len(tokens) == len(words):
        return [WordTiming(t, w.start_s, w.end_s) for t, w in zip(tokens, words, strict=True)]
    start, end = words[0].start_s, words[-1].end_s
    weight = sum(len(t) for t in tokens)
    out: list[WordTiming] = []
    cursor = start
    for i, token in enumerate(tokens):
        stop = end if i == len(tokens) - 1 else cursor + (end - start) * len(token) / weight
        out.append(WordTiming(token, round(cursor, 3), round(stop, 3)))
        cursor = stop
    return out


def language_of(ctx: AppContext, edl: Edl) -> str:
    from reelforge.voice import service as voice_service  # noqa: PLC0415

    try:
        story = voice_service.load_story(ctx, edl.project_id)
    except Exception:  # noqa: BLE001
        story = None
    return LANGUAGES.get(story.language, "en") if story is not None else "en"


async def align_caption(
    ctx: AppContext, edl: Edl, cap: EdlCaption, cache: Path, language: str
) -> list[WordTiming]:
    clip = next((d for d in edl.dialogue if d.scene_id == cap.scene_id), None)
    if clip is None or not cap.text.strip():
        return []
    with ctx.session_factory() as s:
        take = s.get(Artifact, clip.artifact)
    if take is None:
        return []
    audio = ctx.store.absolute_path(take)
    path = cache / f"{cache_key(ctx, take, cap.text)}.json"
    cached = read_cache(path)
    if cached is not None:
        return fit_words(cap.text, cached)
    try:
        words = await ctx.aligner.align(audio, cap.text, language)
    except AlignmentError:
        write_cache(path, None)
        return []
    except Exception:  # noqa: BLE001 - any aligner failure means line-level timing
        return []
    if not words:
        write_cache(path, None)
        return []
    write_cache(path, words)
    return fit_words(cap.text, words)


async def prepare_captions(ctx: AppContext, edl: Edl, out_dir: Path, ass: Path) -> bool:
    """Write `captions.ass`; True when the encode step must burn it in."""
    cache = cache_dir(ctx, edl, out_dir)
    language = language_of(ctx, edl)
    words: dict[str, list[WordTiming]] = {}
    for cap in edl.captions:
        words[cap.scene_id] = await align_caption(ctx, edl, cap, cache, language)
    text = build_ass(edl, words, devanagari_font_family=ctx.settings.devanagari_font_family)
    part_path(ass).write_text(text, encoding="utf-8")
    commit_part(ass)
    if not any(c.text.strip() for c in edl.captions):
        return False
    if not ffmpeg.has_filter("subtitles"):
        if ctx.settings.backend == "mock":
            return False
        raise StepError(STEP, ffmpeg.NO_FFMPEG)
    font = ctx.settings.devanagari_font
    uses_hindi = any(
        resolve_style(edl.caption_style, c) == "hindi_devanagari" or has_devanagari(c.text)
        for c in edl.captions
        if c.text.strip()
    )
    if uses_hindi and not font.is_file():
        raise StepError(STEP, f"Devanagari font not found at {font}. Set it in Settings.")
    return True
