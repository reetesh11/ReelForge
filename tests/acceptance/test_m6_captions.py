"""m6 R6, R7 (renderer side), AC-5, AC-14: .ass presets, safe zones, alignment."""

from __future__ import annotations

import dataclasses
import re

import pytest
from m4_helpers import wav_bytes
from rf_helpers import run_async

HINDI = "नमस्ते दोस्तों"
LATIN = "Arre Aloo itni der kyun aaye ho"


def _edl(captions, style="auto"):
    from reelforge.assembly.edl import Edl, EdlCaption, EdlEndCard, EdlMusic, EdlShot

    return Edl(
        project_id="p",
        video=[EdlShot(scene_id="s1", artifact="a", source_duration_s=6.0, in_s=0.0, out_s=6.0)],
        dialogue=[],
        captions=[
            EdlCaption(scene_id=f"s{i + 1}", speaker="Tamatar", line_no=i + 1, text=t,
                       start_s=a, end_s=b, style=st)
            for i, (t, a, b, st) in enumerate(captions)
        ],
        caption_style=style,
        music=EdlMusic(),
        end_card=EdlEndCard(),
    )


def _styles(ass: str) -> dict[str, dict[str, str]]:
    fmt: list[str] = []
    out: dict[str, dict[str, str]] = {}
    for line in ass.splitlines():
        if line.startswith("Format:") and not fmt and "Fontname" in line:
            fmt = [x.strip() for x in line.removeprefix("Format:").split(",")]
        elif line.startswith("Style:"):
            vals = [x.strip() for x in line.removeprefix("Style:").split(",")]
            out[vals[0]] = dict(zip(fmt, vals))
    return out


def _events(ass: str) -> list[list[str]]:
    return [
        line.removeprefix("Dialogue:").strip().split(",", 9)
        for line in ass.splitlines()
        if line.startswith("Dialogue:")
    ]


def test_safe_zone_constant_is_frozen():
    from reelforge.assembly.captions import SAFE_ZONE, SafeZone

    assert SAFE_ZONE == SafeZone(top=250, bottom=250, left=64, right=64)
    with pytest.raises(dataclasses.FrozenInstanceError):
        SAFE_ZONE.top = 1  # type: ignore[misc]


def test_resolve_style_order():
    from reelforge.assembly.captions import resolve_style
    from reelforge.assembly.edl import EdlCaption

    def cap(text, style=None):
        return EdlCaption(scene_id="s1", speaker=None, line_no=1, text=text, start_s=0, end_s=1, style=style)

    assert resolve_style("auto", cap(LATIN)) == "bold_pop"
    assert resolve_style("auto", cap(HINDI)) == "hindi_devanagari"
    assert resolve_style("clean_subtitle", cap(LATIN)) == "clean_subtitle"
    assert resolve_style("clean_subtitle", cap(HINDI)) == "clean_subtitle"
    assert resolve_style("clean_subtitle", cap(LATIN, "bold_pop")) == "bold_pop"
    assert resolve_style("auto", cap(LATIN, "hindi_devanagari")) == "hindi_devanagari"


def test_ass_header_styles_and_safe_zone_margins():
    from reelforge.assembly.captions import build_ass

    ass = build_ass(_edl([(LATIN, 0.0, 2.0, None)]), {}, devanagari_font_family="Test Devanagari Font")
    assert "PlayResX: 1080" in ass and "PlayResY: 1920" in ass
    styles = _styles(ass)
    assert set(styles) == {"Bold pop", "Clean subtitle", "Hindi Devanagari"}
    for name, st in styles.items():
        assert (st["MarginL"], st["MarginR"], st["MarginV"], st["Alignment"]) == ("64", "64", "250", "2"), name
    assert styles["Hindi Devanagari"]["Fontname"] == "Test Devanagari Font"


def test_one_event_per_non_empty_caption_with_resolved_style_and_times():
    from reelforge.assembly.captions import build_ass

    edl = _edl(
        [(LATIN, 1.0, 3.5, None), (HINDI, 4.0, 5.25, None), ("", 5.5, 6.0, None), ("Plain line", 0.5, 0.9, "clean_subtitle")]
    )
    events = _events(build_ass(edl, {}, devanagari_font_family="F"))
    assert len(events) == 3
    by_start = {e[1]: e for e in events}
    assert by_start["0:00:01.00"][2] == "0:00:03.50" and by_start["0:00:01.00"][3] == "Bold pop"
    assert by_start["0:00:04.00"][2] == "0:00:05.25" and by_start["0:00:04.00"][3] == "Hindi Devanagari"
    assert by_start["0:00:00.50"][3] == "Clean subtitle"
    assert HINDI in by_start["0:00:04.00"][9]


def test_edl_style_applies_to_every_caption_without_its_own():
    from reelforge.assembly.captions import build_ass

    edl = _edl([(LATIN, 0.0, 1.0, None), (HINDI, 1.0, 2.0, None)], style="clean_subtitle")
    assert {e[3] for e in _events(build_ass(edl, {}, devanagari_font_family="F"))} == {"Clean subtitle"}


def test_bold_pop_uses_karaoke_only_when_words_are_known():
    from reelforge.assembly.align import ProportionalAligner  # noqa: F401  (module must exist)
    from reelforge.assembly.captions import WordTiming, build_ass

    edl = _edl([("Hello world", 1.0, 3.0, None)])
    words = {"s1": [WordTiming("Hello", 0.0, 0.5), WordTiming("world", 0.5, 1.5)]}
    text = _events(build_ass(edl, words, devanagari_font_family="F"))[0][9]
    assert re.search(r"\\k50[}\\]", text) and re.search(r"\\k100[}\\]", text)
    assert "Hello" in text and "world" in text
    plain = _events(build_ass(edl, {}, devanagari_font_family="F"))[0][9]
    assert "\\k" not in plain and "Hello world" in plain
    assert "\\k" not in _events(build_ass(edl, {"s1": []}, devanagari_font_family="F"))[0][9]


def test_word_timing_is_frozen():
    from reelforge.assembly.captions import WordTiming

    w = WordTiming("a", 0.0, 1.0)
    assert (w.text, w.start_s, w.end_s) == ("a", 0.0, 1.0)
    with pytest.raises(dataclasses.FrozenInstanceError):
        w.text = "b"  # type: ignore[misc]


def test_proportional_aligner_splits_clip_by_characters(tmp_path):
    from reelforge.assembly.align import ProportionalAligner

    audio = tmp_path / "a.wav"
    audio.write_bytes(wav_bytes(2.0, rate=8000))
    al = ProportionalAligner()
    words = run_async(al.align(audio, "ab cdef gh", "en"))
    assert [w.text for w in words] == ["ab", "cdef", "gh"]
    assert words[0].start_s == pytest.approx(0.0, abs=0.01)
    assert words[-1].end_s == pytest.approx(2.0, abs=0.05)
    assert [w.end_s - w.start_s for w in words] == pytest.approx([0.5, 1.0, 0.5], abs=0.03)
    for a, b in zip(words, words[1:]):
        assert b.start_s == pytest.approx(a.end_s, abs=0.01)
    assert run_async(al.align(audio, "ab cdef gh", "en")) == words


def test_context_aligner_default_and_injection(tmp_path):
    from reelforge.assembly.align import ProportionalAligner
    from reelforge.context import AppContext
    from rf_helpers import make_ctx, make_settings, passing_report

    s = make_settings(tmp_path)
    ctx = make_ctx(s)
    assert isinstance(ctx.aligner, ProportionalAligner)
    ctx.close()

    class Stub:
        async def align(self, audio, text, language):
            return []

    stub = Stub()

    async def _noop() -> None:
        return None

    ctx2 = AppContext.create(
        make_settings(tmp_path / "two"), adapter=None, available_gb=lambda: 64.0,
        ollama_unload=_noop, doctor=lambda: passing_report(), aligner=stub,
    )
    assert ctx2.aligner is stub
    ctx2.close()
