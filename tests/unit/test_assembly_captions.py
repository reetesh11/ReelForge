from __future__ import annotations

from reelforge.assembly.captions import SAFE_ZONE, WordTiming, build_ass, has_devanagari
from reelforge.assembly.edl import Edl, EdlCaption, EdlShot


def _edl(text: str, style: str = "auto") -> Edl:
    shot = EdlShot(scene_id="s1", artifact="a", source_duration_s=5, in_s=0, out_s=5)
    cap = EdlCaption(scene_id="s1", speaker=None, line_no=1, text=text, start_s=0.5, end_s=2.0)
    return Edl(project_id="p", video=[shot], dialogue=[], captions=[cap], caption_style=style)


def test_safe_zone_margins_in_every_style() -> None:
    ass = build_ass(_edl("hello"), {}, devanagari_font_family="F")
    styles = [ln for ln in ass.splitlines() if ln.startswith("Style:")]
    assert len(styles) == 3
    for ln in styles:
        cols = ln.split(",")
        assert cols[-4:-1] == [str(SAFE_ZONE.left), str(SAFE_ZONE.right), str(SAFE_ZONE.bottom)]


def test_karaoke_offsets_and_text_edit() -> None:
    words = {"s1": [WordTiming("a", 0.2, 0.5), WordTiming("b", 0.5, 1.0)]}
    ass = build_ass(_edl("a b"), words, devanagari_font_family="F")
    assert "{\\k20}{\\k30}a {\\k50}b" in ass
    edited = build_ass(_edl("changed words"), {}, devanagari_font_family="F")
    assert "changed words" in edited and "\\k" not in edited


def test_devanagari_detection_and_font() -> None:
    assert has_devanagari("नमस्ते") and not has_devanagari("namaste")
    ass = build_ass(_edl("नमस्ते"), {}, devanagari_font_family="Fam")
    assert "Hindi Devanagari,,0,0,0,,नमस्ते" in ass and "Style: Hindi Devanagari,Fam," in ass


def test_empty_caption_makes_no_event() -> None:
    assert "Dialogue:" not in build_ass(_edl("  "), {}, devanagari_font_family="F")
