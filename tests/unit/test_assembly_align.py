"""Caption alignment: word timing, line fallback, cache and font checks."""

from __future__ import annotations

import asyncio
import wave
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from reelforge.assembly import caption_step, ffmpeg
from reelforge.assembly.align import AlignmentError, ProportionalAligner
from reelforge.assembly.captions import WordTiming
from reelforge.assembly.edl import Edl, EdlCaption
from reelforge.assembly.state import StepError


def _wav(path: Path, seconds: float = 1.0) -> Path:
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(8000)
        w.writeframes(b"\0\0" * int(8000 * seconds))
    return path


def test_proportional_aligner_is_deterministic_and_covers_clip(tmp_path: Path) -> None:
    clip = _wav(tmp_path / "a.wav", 2.0)
    al = ProportionalAligner()
    first = asyncio.run(al.align(clip, "ab cdef", "en"))
    assert first == asyncio.run(al.align(clip, "ab cdef", "en"))
    assert first[0].start_s == 0.0
    assert first[-1].end_s == pytest.approx(2.0)
    assert asyncio.run(al.align(clip, "   ", "en")) == []


def test_fit_words_keeps_timing_when_counts_match_and_spreads_otherwise() -> None:
    words = [WordTiming("a", 0.0, 0.5), WordTiming("b", 0.5, 1.0)]
    same = caption_step.fit_words("x y", words)
    assert [(w.text, w.start_s, w.end_s) for w in same] == [("x", 0.0, 0.5), ("y", 0.5, 1.0)]
    spread = caption_step.fit_words("x y z", words)
    assert len(spread) == 3
    assert spread[0].start_s == 0.0
    assert spread[-1].end_s == pytest.approx(1.0)
    assert caption_step.fit_words("", words) == []


def test_cache_round_trip_and_failure_marker(tmp_path: Path) -> None:
    path = tmp_path / "c" / "k.json"
    assert caption_step.read_cache(path) is None
    caption_step.write_cache(path, [WordTiming("hi", 0.0, 0.4)])
    assert caption_step.read_cache(path) == [WordTiming("hi", 0.0, 0.4)]
    caption_step.write_cache(path, None)
    assert caption_step.read_cache(path) == []


class _Stub:
    id = "stub"

    def __init__(self, result: Any) -> None:
        self.result = result
        self.calls = 0

    async def align(self, audio: Path, text: str, language: str) -> list[WordTiming]:
        self.calls += 1
        if isinstance(self.result, Exception):
            raise self.result
        return self.result


class _Store:
    def __init__(self, root: Path) -> None:
        self.root = root

    def absolute_path(self, take: Any) -> Path:
        return self.root / "a.wav"


class _Session:
    def __init__(self, take: Any) -> None:
        self.take = take

    def __enter__(self) -> _Session:
        return self

    def __exit__(self, *a: object) -> None:
        return None

    def get(self, model: Any, key: Any) -> Any:
        return self.take


def _ctx(tmp_path: Path, aligner: _Stub) -> Any:
    _wav(tmp_path / "a.wav")
    take = SimpleNamespace(sha256="abc")
    return SimpleNamespace(
        aligner=aligner,
        store=_Store(tmp_path),
        session_factory=lambda: _Session(take),
    )


def _edl() -> Edl:
    from reelforge.assembly.edl import EdlDialogue

    return Edl(
        project_id="p",
        video=[],
        dialogue=[EdlDialogue(scene_id="s1", artifact="t", offset_s=0, duration_s=1)],
        captions=[
            EdlCaption(
                scene_id="s1", speaker="A", line_no=1, text="hello there", start_s=0, end_s=1
            )
        ],
    )


def _run(ctx: Any, tmp_path: Path) -> list[WordTiming]:
    edl = _edl()
    return asyncio.run(
        caption_step.align_caption(ctx, edl, edl.captions[0], tmp_path / "cache", "en")
    )


def test_word_timing_then_cache_hit_skips_aligner(tmp_path: Path) -> None:
    stub = _Stub([WordTiming("hello", 0.0, 0.4), WordTiming("there", 0.4, 0.9)])
    ctx = _ctx(tmp_path, stub)
    assert len(_run(ctx, tmp_path)) == 2
    assert len(_run(ctx, tmp_path)) == 2
    assert stub.calls == 1


@pytest.mark.parametrize("result", [AlignmentError("boom"), RuntimeError("boom"), []])
def test_failure_or_empty_result_falls_back_to_line_timing(tmp_path: Path, result: Any) -> None:
    ctx = _ctx(tmp_path, _Stub(result))
    assert _run(ctx, tmp_path) == []


def test_missing_font_raises_for_real_backend(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(ffmpeg, "has_filter", lambda name: True)
    monkeypatch.setattr(caption_step, "cache_dir", lambda c, e, o: tmp_path / "cache")
    stub = _Stub([])
    ctx = _ctx(tmp_path, stub)
    font = tmp_path / "missing.ttc"
    ctx.settings = SimpleNamespace(backend="real", devanagari_font=font, devanagari_font_family="F")
    edl = _edl().model_copy(update={"caption_style": "hindi_devanagari"})
    with pytest.raises(StepError) as err:
        asyncio.run(caption_step.prepare_captions(ctx, edl, tmp_path, tmp_path / "captions.ass"))
    assert str(err.value) == f"Devanagari font not found at {font}. Set it in Settings."


def test_mock_backend_skips_burn_without_subtitles_filter(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(ffmpeg, "has_filter", lambda name: False)
    monkeypatch.setattr(caption_step, "cache_dir", lambda c, e, o: tmp_path / "cache")
    ctx = _ctx(tmp_path, _Stub([]))
    ctx.settings = SimpleNamespace(
        backend="mock", devanagari_font=tmp_path, devanagari_font_family="F"
    )
    ass = tmp_path / "captions.ass"
    assert asyncio.run(caption_step.prepare_captions(ctx, _edl(), tmp_path, ass)) is False
    assert ass.is_file()
