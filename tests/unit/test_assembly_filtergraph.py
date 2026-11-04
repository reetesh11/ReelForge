from __future__ import annotations

import re

from reelforge.assembly.edl import Edl, EdlDialogue, EdlShot
from reelforge.assembly.filtergraph import (
    FINAL,
    PREVIEW,
    Chain,
    Filter,
    FilterGraph,
    build_dialogue_graph,
    build_encode_graph,
    build_join_graph,
    build_loudnorm_graph,
    build_normalise_graph,
    escape,
)


def _edl(fade: float = 0.0) -> Edl:
    shots = [
        EdlShot(
            scene_id=f"s{i}",
            artifact=f"a{i}",
            source_duration_s=2.0,
            in_s=0.0,
            out_s=2.0,
            transition_in_s=fade if i else 0.0,
        )
        for i in range(3)
    ]
    dlg = [EdlDialogue(scene_id="s1", artifact="v1", offset_s=2.5, duration_s=1.0)]
    return Edl(project_id="p", video=shots, dialogue=dlg, captions=[])


def test_escape_quotes_only_special_values() -> None:
    assert escape("plain") == "plain"
    assert escape(1.5) == "1.5"
    assert escape("a:b") == "'a:b'"
    assert escape("it's") == "'it'\\''s'"


def test_serialisation() -> None:
    g = FilterGraph(
        [Chain([], [Filter("anullsrc", {"d": 2})], ["x"]), Chain(["x"], [Filter("null")], ["y"])]
    )
    assert g.to_script() == "anullsrc=d=2[x];\n[x]null[y]"


def test_join_uses_xfade_for_fades_and_concat_for_cuts() -> None:
    script = build_join_graph(_edl(0.5)).to_script()
    assert script.count("xfade=") == 2 and "concat" not in script
    assert "offset=1.5" in script
    cuts = build_join_graph(_edl(0.0)).to_script()
    assert cuts.count("concat=") == 2 and "xfade" not in cuts
    assert (
        build_join_graph(_edl().model_copy(update={"video": _edl().video[:1]})).to_script()
        == "[0:v]null[v]"
    )


def test_dialogue_clips_are_delayed_in_milliseconds() -> None:
    script = build_dialogue_graph(_edl()).to_script()
    assert "adelay=delays='2500|2500'" in script or "adelay=delays=2500|2500" in script
    assert "amix=inputs=2" in script and "normalize=0" in script


def test_loudnorm_passes() -> None:
    first = build_loudnorm_graph().to_script()
    assert "print_format=json" in first and "measured_I" not in first
    vals = {
        "input_i": "-20.1",
        "input_tp": "-3.0",
        "input_lra": "2.0",
        "input_thresh": "-30.5",
        "target_offset": "0.4",
    }
    second = build_loudnorm_graph(vals).to_script()
    assert "measured_I=-20.1" in second and "linear=true" in second


def _numbers_masked(text: str) -> str:
    return re.sub(r"\d+", "N", text)


def test_preview_and_final_differ_only_in_size_values() -> None:
    shot = _edl().video[0]
    a = build_normalise_graph(shot, PREVIEW.width, PREVIEW.height).to_script()
    b = build_normalise_graph(shot, FINAL.width, FINAL.height).to_script()
    assert a != b and _numbers_masked(a) == _numbers_masked(b)
    ea = build_encode_graph(PREVIEW, None, None).to_script()
    eb = build_encode_graph(FINAL, None, None).to_script()
    assert ea != eb and _numbers_masked(ea) == _numbers_masked(eb)


def test_encode_graph_burns_captions_when_given() -> None:
    script = build_encode_graph(FINAL, "/tmp/a b/captions.ass", "/fonts").to_script()
    assert "subtitles=filename='/tmp/a b/captions.ass':fontsdir=/fonts" in script
