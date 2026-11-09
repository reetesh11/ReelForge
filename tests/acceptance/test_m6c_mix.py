"""m6c R6-R8, AC-4, AC-5, AC-6: the mix graph, measured on known tones.

Each test builds an `Edl` by hand, runs `build_mix_graph(edl)` through ffmpeg
(`-filter_complex_script`, no shell) with a dialogue bed (1 kHz) and cue files
(music 220 Hz, sfx 880 Hz, ambience 330 Hz), and measures the result per
frequency, so each cue is heard on its own.
"""

from __future__ import annotations

import pytest
from m6c_helpers import (
    DIALOGUE_HZ,
    FREQ,
    dialogue_file,
    duration_of,
    edl_cue,
    goertzel_db,
    make_edl,
    onset_s,
    run_mix,
    tone_file,
)

TOTAL = 20.0


def _files(tmp_path, *kinds_and_len):
    out = []
    for i, (kind, seconds) in enumerate(kinds_and_len):
        out.append(tone_file(tmp_path / f"{kind}{i}.wav", FREQ[kind], seconds))
    return out


# AC-4: levels and start times --------------------------------------------------------------


def test_each_cue_is_louder_inside_its_window_than_just_outside_and_starts_on_time(tmp_path):
    audio = [
        edl_cue("m", "music", 3.0, 9.0),
        edl_cue("s", "sfx", 11.0, 12.5),
        edl_cue("a", "ambience", 14.0, 18.0),
    ]
    edl = make_edl(TOTAL, audio, dialogue=(5.0, 2.0))
    files = _files(tmp_path, ("music", 6.0), ("sfx", 1.5), ("ambience", 4.0))
    mix = run_mix(tmp_path, edl, dialogue_file(tmp_path / "d.wav", TOTAL, 5.0, 2.0), files)
    assert duration_of(mix) == pytest.approx(TOTAL, abs=0.06)
    for c, kind in zip(audio, ("music", "sfx", "ambience"), strict=True):
        f = FREQ[kind]
        inside = goertzel_db(mix, f, c.start_s + 0.25, c.end_s - 0.25)
        before = goertzel_db(mix, f, c.start_s - 0.5, c.start_s - 0.1)
        after = goertzel_db(mix, f, c.end_s + 0.1, c.end_s + 0.5)
        assert inside > -40.0
        assert inside > before + 20.0 and inside > after + 20.0, (kind, inside, before, after)
        assert onset_s(mix, f, c.start_s) == pytest.approx(c.start_s, abs=0.05), kind
    # dialogue is still there
    assert goertzel_db(mix, DIALOGUE_HZ, 5.2, 6.8) > -30.0


def test_the_per_cue_gain_is_applied(tmp_path):
    levels = []
    for i, gain in enumerate((0.0, -12.0)):
        edl = make_edl(TOTAL, [edl_cue("m", "music", 2.0, 8.0, gain=gain)])
        mix = run_mix(
            tmp_path, edl, dialogue_file(tmp_path / f"d{i}.wav", TOTAL, 15.0, 1.0),
            _files(tmp_path, ("music", 6.0)), name=f"g{i}",
        )
        levels.append(goertzel_db(mix, FREQ["music"], 3.0, 7.0))
    assert levels[0] - levels[1] == pytest.approx(12.0, abs=1.5)


def test_fade_in_and_fade_out_shape_the_cue_edges(tmp_path):
    edl = make_edl(TOTAL, [edl_cue("a", "ambience", 4.0, 12.0, fade_in=2.0, fade_out=2.0)])
    mix = run_mix(
        tmp_path, edl, dialogue_file(tmp_path / "d.wav", TOTAL, 15.0, 1.0), _files(tmp_path, ("ambience", 8.0))
    )
    f = FREQ["ambience"]
    steady = goertzel_db(mix, f, 7.0, 9.0)
    assert goertzel_db(mix, f, 4.0, 4.4) < steady - 8.0
    assert goertzel_db(mix, f, 11.6, 12.0) < steady - 8.0
    assert goertzel_db(mix, f, 5.8, 6.2) > goertzel_db(mix, f, 4.0, 4.4)


def test_a_cue_that_runs_past_the_reel_end_is_cut_there(tmp_path):
    edl = make_edl(TOTAL, [edl_cue("m", "music", 15.0, 30.0)])
    mix = run_mix(
        tmp_path, edl, dialogue_file(tmp_path / "d.wav", TOTAL, 2.0, 1.0), _files(tmp_path, ("music", 15.0))
    )
    assert duration_of(mix) == pytest.approx(TOTAL, abs=0.06)
    assert goertzel_db(mix, FREQ["music"], 16.0, 19.5) > -40.0


def test_overlapping_cues_of_the_same_kind_are_mixed_together(tmp_path):
    audio = [edl_cue("m1", "music", 2.0, 10.0), edl_cue("m2", "music", 6.0, 14.0)]
    edl = make_edl(TOTAL, audio)
    files = _files(tmp_path, ("music", 8.0), ("music", 8.0))
    mix = run_mix(tmp_path, edl, dialogue_file(tmp_path / "d.wav", TOTAL, 17.0, 1.0), files)
    f = FREQ["music"]
    assert goertzel_db(mix, f, 3.0, 5.0) > -40.0 and goertzel_db(mix, f, 11.0, 13.0) > -40.0
    assert goertzel_db(mix, f, 7.0, 9.0) > goertzel_db(mix, f, 3.0, 5.0) + 1.0


# AC-5: ducking ------------------------------------------------------------------------------


def _duck_mix(tmp_path, *, duck, mix_settings=None, name="duck"):
    edl = make_edl(
        TOTAL,
        [edl_cue("m", "music", 0.0, TOTAL, duck=duck)],
        dialogue=(8.0, 4.0),
        mix=mix_settings,
    )
    return run_mix(
        tmp_path, edl, dialogue_file(tmp_path / f"{name}.wav", TOTAL, 8.0, 4.0),
        _files(tmp_path, ("music", TOTAL)), name=name,
    )


def _music(mix, t0, t1):
    return goertzel_db(mix, FREQ["music"], t0, t1)


def test_music_drops_by_the_default_nine_db_under_dialogue_and_comes_back(tmp_path):
    mix = _duck_mix(tmp_path, duck=True)
    before, during, after = _music(mix, 4.0, 6.0), _music(mix, 9.0, 11.0), _music(mix, 14.0, 16.0)
    assert before - during == pytest.approx(9.0, abs=1.5)
    assert after == pytest.approx(before, abs=1.0)
    assert goertzel_db(mix, DIALOGUE_HZ, 9.0, 11.0) > -30.0


def test_ducking_applies_an_attack_and_a_release_not_a_step(tmp_path):
    mix = _duck_mix(tmp_path, duck=True)
    before = _music(mix, 4.0, 6.0)
    # attack (150 ms): the first 50 ms of the line is not yet fully ducked
    assert before - _music(mix, 8.0, 8.05) < 7.5
    # release (400 ms): the first 100 ms after the line is still clearly ducked
    assert before - _music(mix, 12.0, 12.1) > 3.0
    # and the music is back after the release time
    assert before - _music(mix, 12.5, 12.6) < 1.5


def test_music_without_duck_is_unchanged_under_dialogue(tmp_path):
    mix = _duck_mix(tmp_path, duck=False, name="noduck")
    assert _music(mix, 4.0, 6.0) - _music(mix, 9.0, 11.0) == pytest.approx(0.0, abs=0.5)


def test_the_project_ducking_amount_sets_the_drop(tmp_path):
    from reelforge.assembly.edl import EdlMix

    mix = _duck_mix(tmp_path, duck=True, mix_settings=EdlMix(duck_db=15.0), name="duck15")
    assert _music(mix, 4.0, 6.0) - _music(mix, 9.0, 11.0) == pytest.approx(15.0, abs=1.5)


def test_only_music_is_ducked_not_sfx_or_ambience(tmp_path):
    audio = [
        edl_cue("m", "music", 0.0, TOTAL, duck=True),
        edl_cue("s", "sfx", 0.0, TOTAL, duck=True),
        edl_cue("a", "ambience", 0.0, TOTAL, duck=True),
    ]
    edl = make_edl(TOTAL, audio, dialogue=(8.0, 4.0))
    files = _files(tmp_path, ("music", TOTAL), ("sfx", TOTAL), ("ambience", TOTAL))
    mix = run_mix(tmp_path, edl, dialogue_file(tmp_path / "d.wav", TOTAL, 8.0, 4.0), files)
    assert _music(mix, 4.0, 6.0) - _music(mix, 9.0, 11.0) == pytest.approx(9.0, abs=1.5)
    for kind in ("sfx", "ambience"):
        f = FREQ[kind]
        assert goertzel_db(mix, f, 4.0, 6.0) - goertzel_db(mix, f, 9.0, 11.0) == pytest.approx(0.0, abs=0.5)


# AC-6: silence ----------------------------------------------------------------------------


def _silence_edl(mix_settings=None):
    audio = [
        edl_cue("m", "music", 0.0, TOTAL),
        edl_cue("s", "sfx", 5.0, 15.0),
        edl_cue("a", "ambience", 0.0, TOTAL),
        edl_cue("hush", "silence", 10.0, 12.0),
    ]
    return make_edl(TOTAL, audio, dialogue=(9.0, 4.0), mix=mix_settings)


def _silence_files(tmp_path):
    return _files(tmp_path, ("music", TOTAL), ("sfx", 10.0), ("ambience", TOTAL))


def test_a_silence_cue_takes_music_sfx_and_ambience_below_minus_60_db_but_not_dialogue(tmp_path):
    mix = run_mix(
        tmp_path, _silence_edl(), dialogue_file(tmp_path / "d.wav", TOTAL, 9.0, 4.0), _silence_files(tmp_path)
    )
    for kind in ("music", "sfx", "ambience"):
        f = FREQ[kind]
        assert goertzel_db(mix, f, 10.2, 11.8) < -60.0, kind
        assert goertzel_db(mix, f, 7.0, 9.0) > -40.0, kind
        assert goertzel_db(mix, f, 13.0, 14.5) > -40.0, kind
    assert goertzel_db(mix, DIALOGUE_HZ, 10.2, 11.8) > -30.0


def test_the_silence_fades_are_short_and_use_the_project_setting(tmp_path):
    from reelforge.assembly.edl import EdlMix

    dlg = dialogue_file(tmp_path / "d.wav", TOTAL, 9.0, 4.0)
    quick = run_mix(tmp_path, _silence_edl(), dlg, _silence_files(tmp_path), name="q")
    music = FREQ["music"]
    assert goertzel_db(quick, music, 9.8, 10.0) > -40.0  # nothing happens before the cue starts
    assert goertzel_db(quick, music, 12.1, 12.3) > -40.0  # back at full level after the 80 ms fade
    slow = run_mix(tmp_path, _silence_edl(EdlMix(silence_fade_s=0.5)), dlg, _silence_files(tmp_path), name="s")
    outside = goertzel_db(slow, music, 13.0, 14.0)
    assert goertzel_db(slow, music, 12.1, 12.3) < outside - 4.0
    assert goertzel_db(slow, music, 10.0, 10.1) > outside - 4.0  # still fading down


# graph shape -------------------------------------------------------------------------------


def test_the_graph_is_a_filter_script_with_a_mix_output_and_one_input_per_cue_file():
    from reelforge.assembly.filtergraph import build_mix_graph

    audio = [
        edl_cue("m", "music", 0.0, 5.0),
        edl_cue("hush", "silence", 2.0, 3.0),
        edl_cue("s", "sfx", 1.0, 2.0),
    ]
    script = build_mix_graph(make_edl(TOTAL, audio, dialogue=(1.0, 1.0))).to_script()
    assert "[mix]" in script
    assert "[0:a]" in script and "[1:a]" in script and "[2:a]" in script
    assert "[3:a]" not in script, "a silence cue has no input file"
