from reelforge.assembly.edl import Edl, EdlAudio, EdlDialogue, EdlMix, EdlShot
from reelforge.assembly.filtergraph import build_mix_graph, duck_expression, silence_expression


def _edl(audio, dialogue=(), mix=None):
    dlg = [
        EdlDialogue(scene_id=f"s{i}", artifact="d", offset_s=o, duration_s=d)
        for i, (o, d) in enumerate(dialogue, start=1)
    ]
    extra = {"mix": mix} if mix is not None else {}
    return Edl(
        project_id="p",
        video=[EdlShot(scene_id="s1", artifact="v", source_duration_s=20, in_s=0, out_s=20)],
        dialogue=dlg,
        captions=[],
        audio=audio,
        **extra,
    )


def _cue(id_, kind, start, end, **kw):
    base = {"gain_db": 0.0, "fade_in_s": 0.0, "fade_out_s": 0.0, "duck": False}
    base.update(kw)
    return EdlAudio(
        cue_id=id_, kind=kind, artifact=None if kind == "silence" else "x",
        start_s=start, end_s=end, **base,
    )  # fmt: skip


def test_no_cues_is_exactly_the_dialogue_only_graph():
    assert build_mix_graph(_edl([])).to_script() == (
        "[0:a]apad=whole_dur=20,atrim=duration=20,"
        "aformat=sample_fmts=fltp:sample_rates=48000:channel_layouts=stereo[mix]"
    )


def test_two_dialogue_lines_give_one_max_of_two_ramps():
    expr = duck_expression(_edl([], dialogue=[(2.0, 1.0), (8.0, 2.0)], mix=EdlMix(duck_db=6.0)))
    assert expr is not None
    assert expr.startswith("1-0.498813*")  # 6 dB is a gain of 0.501, so the drop is 0.499
    assert expr.count("min(clip(") == 2 and "max(" in expr
    assert "(t-2)/0.15" in expr and "(t-8)/0.15" in expr and "(t-10)/0.4" in expr


def test_no_dialogue_or_no_drop_means_no_duck_expression():
    assert duck_expression(_edl([])) is None
    assert duck_expression(_edl([], dialogue=[(1.0, 1.0)], mix=EdlMix(duck_db=0.0))) is None


def test_silence_gates_the_bus_only():
    audio = [_cue("m", "music", 0, 20), _cue("hush", "silence", 5.0, 7.0)]
    script = build_mix_graph(_edl(audio, dialogue=[(1.0, 1.0)])).to_script()
    assert silence_expression(_edl(audio)) is not None
    assert "[c1]" in script and "[bus]" in script and "[1:a]" in script
    assert script.count("eval=frame") == 1
    assert "[dlg][bus]amix=" in script


def test_a_ducked_music_cue_adds_the_duck_envelope_and_sfx_does_not():
    audio = [_cue("m", "music", 0, 20, duck=True), _cue("s", "sfx", 1, 2, duck=True)]
    script = build_mix_graph(_edl(audio, dialogue=[(3.0, 1.0)])).to_script()
    assert script.count("eval=frame") == 1


def test_only_silence_cues_leave_the_dialogue_alone():
    script = build_mix_graph(_edl([_cue("hush", "silence", 1, 2)])).to_script()
    assert "[mix]" in script and "[1:a]" not in script and "[bus]" not in script
