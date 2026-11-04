"""m6c R1-R3, AC-1: the `audio` cue list in the story schema, its messages and time resolution."""

from __future__ import annotations

import json

import pytest
from m6c_helpers import at, cue, get_audio, light_world, story_with_audio
from rf_helpers import create_project
from story_helpers import put, story_dict


def _parse(audio, **over):
    from reelforge.story.yamlio import parse_story

    return parse_story(story_with_audio(audio, **over))


def _errors(audio, **over):
    from reelforge.story.errors import StoryInvalid

    with pytest.raises(StoryInvalid) as ei:
        _parse(audio, **over)
    return {(e.path, e.message) for e in ei.value.errors}


GOOD = [
    cue("gong1", "sfx", at("s2", 1.0), duration=1.5, prompt="gong slam", gain_db=-3.0, fade_out_s=0.2),
    cue("bed", "music", at("s1"), end=at("s5", at_="scene_end"), duck=True, fade_in_s=1.0),
    cue("hush", "silence", at("s3"), end=at("s3", at_="scene_end")),
]


def test_a_story_with_an_audio_list_validates_and_keeps_every_field():
    from reelforge.story.yamlio import parse_story, story_to_yaml

    story = _parse(GOOD)
    assert [c.id for c in story.audio] == ["gong1", "bed", "hush"]
    g, b, h = story.audio
    assert (g.kind, g.source, g.prompt, g.gain_db, g.fade_out_s) == ("sfx", "generate", "gong slam", -3.0, 0.2)
    assert (g.start.scene, g.start.at, g.start.offset, g.duration, g.end) == ("s2", "scene_start", 1.0, 1.5, None)
    assert (b.end.scene, b.end.at, b.duck, b.fade_in_s, b.state) == ("s5", "scene_end", True, 1.0, None)
    assert h.kind == "silence"
    assert parse_story(story_to_yaml(story)) == story


def test_a_cue_can_be_a_suggested_one_but_no_other_state_is_stored():
    from reelforge.story.errors import StoryInvalid

    ok = _parse([cue("c1", "sfx", at("s1"), duration=1.0, state="suggested")])
    assert ok.audio[0].state == "suggested"
    with pytest.raises(StoryInvalid):
        _parse([cue("c1", "sfx", at("s1"), duration=1.0, state="ready")])


def test_an_unknown_cue_field_is_rejected_with_its_path():
    errs = _errors([cue("c1", "sfx", at("s1"), duration=1.0, volume=3)])
    assert ("audio[0].volume", "unknown field") in errs


@pytest.mark.parametrize(
    "bad, message",
    [
        (cue("gong1", "sfx", at("s99"), duration=1.0), 'Cue "gong1": unknown scene "s99".'),
        (cue("gong1", "sfx", at("s1"), end=at("s99"), ), 'Cue "gong1": unknown scene "s99".'),
        (cue("gong1", "sfx", at("s1", -1.0), duration=1.0), 'Cue "gong1": start must not be negative.'),
        (cue("gong1", "sfx", at("s2"), end=at("s1", -0.5)), 'Cue "gong1": end must not be negative.'),
        (cue("gong1", "sfx", at("s1"), duration=-1.0), 'Cue "gong1": duration must not be negative.'),
        (
            cue("gong1", "sfx", at("s2", 1.0), end=at("s1", 2.0)),
            'Cue "gong1": end (2.0 s) is before start (3.0 s).',
        ),
        (
            cue("gong1", "sfx", at("s2", 1.0), end=at("s2", 1.0)),
            'Cue "gong1": end (3.0 s) is not after start (3.0 s).',
        ),
        (
            cue("gong1", "boom", at("s1"), duration=1.0),
            'Cue "gong1": unknown kind "boom"; use music, sfx, ambience or silence.',
        ),
        (cue("gong1", "sfx", at("s1"), duration=1.0, end=at("s2")), 'Cue "gong1": give either end or duration.'),
        (cue("gong1", "sfx", at("s1")), 'Cue "gong1": give either end or duration.'),
    ],
)
def test_each_bad_cue_is_rejected_with_a_message_naming_the_cue_and_the_problem(bad, message):
    assert ("audio[0]", message) in _errors([bad])


def test_a_duplicate_cue_id_is_rejected():
    a = cue("gong1", "sfx", at("s1"), duration=1.0)
    b = cue("gong1", "sfx", at("s2"), duration=1.0)
    errs = _errors([a, b])
    assert any(m == 'Cue "gong1": id is used more than once.' and p.startswith("audio[") for p, m in errs)


def test_an_empty_prompt_is_not_a_story_validation_error():
    story = _parse([cue("c1", "sfx", at("s1"), duration=1.0, prompt="")])
    assert story.audio[0].prompt == ""


def test_a_silence_cue_ignores_prompt_source_and_duck():
    story = _parse([cue("s", "silence", at("s1"), duration=1.0, prompt="x", source="file", duck=True)])
    assert story.audio[0].kind == "silence"


def test_a_story_with_audio_and_the_old_music_block_loads():
    from reelforge.story.yamlio import parse_story

    d = json.loads(story_with_audio(GOOD))
    d["music"] = {"mode": "library", "track": "festive_dhol_01", "duck_under_speech": True}
    story = parse_story(json.dumps(d))
    assert story.music is not None and len(story.audio) == 3


def test_story_timeline_sums_durations_and_spreads_target_seconds_over_unset_ones():
    from reelforge.story.audio import story_timeline
    from reelforge.story.yamlio import parse_story

    d = story_dict(4, target_seconds=12)
    d["scenes"][1].pop("duration")
    d["scenes"][3].pop("duration")
    tl = story_timeline(parse_story(json.dumps(d)))
    # a scene without a duration takes target_seconds / len(scenes) = 3.0 s
    assert tl == {"s1": (0.0, 2.0), "s2": (2.0, 5.0), "s3": (5.0, 7.0), "s4": (7.0, 10.0)}


def test_resolve_cue_gives_absolute_start_and_end():
    from reelforge.story.audio import resolve_cue

    story = _parse([
        cue("a", "sfx", at("s2", 1.5), duration=1.0),
        cue("b", "music", at("s1"), end=at("s5", at_="scene_end")),
        cue("c", "sfx", at("s3", at_="scene_end"), duration=0.5),
        cue("d", "sfx", at("s3", 0.25), end=at("s4", 0.5)),
    ])
    got = {c.id: resolve_cue(story, c) for c in story.audio}
    assert got["a"] == pytest.approx((3.5, 4.5))
    assert got["b"] == pytest.approx((0.0, 10.0))
    assert got["c"] == pytest.approx((6.0, 6.5))
    assert got["d"] == pytest.approx((4.25, 6.5))


def test_default_gains_per_kind():
    from reelforge.story.audio import KIND_DEFAULT_GAIN_DB

    assert KIND_DEFAULT_GAIN_DB == {"music": -12.0, "sfx": -6.0, "ambience": -18.0}


def test_saving_a_bad_cue_over_http_returns_422_naming_the_cue(tmp_path):
    from rf_helpers import make_client, make_ctx, make_settings

    ctx = make_ctx(make_settings(tmp_path))
    with make_client(ctx) as client:
        pid = create_project(client)["id"]
        bad = story_with_audio([cue("gong1", "sfx", at("s99"), duration=1.0)])
        r = put(client, pid, bad)
        assert r.status_code == 422, r.text
        body = r.json()
        assert body["detail"] == "story.yaml is invalid"
        assert {"path": "audio[0]", "message": 'Cue "gong1": unknown scene "s99".'} in [
            {"path": e["path"], "message": e["message"]} for e in body["errors"]
        ]


def test_the_old_music_note_is_ignored_once_audio_exists(tmp_path):
    """R3: with only `music` the Sound screen gets a hint and no cues; with `audio` the hint is gone."""
    music = {"mode": "library", "track": "festive_dhol_01", "duck_under_speech": True}
    only_music = json.dumps(story_dict(5, music=music))
    with light_world(tmp_path / "a", text=only_music) as (_, client, pid):
        out = get_audio(client, pid)
        assert out["cues"] == [] and out["legacy_music_hint"] is True
    both = json.dumps(story_dict(5, music=music, audio=[cue("a", "sfx", at("s1"), duration=1.0)]))
    with light_world(tmp_path / "b", text=both) as (_, client, pid):
        out = get_audio(client, pid)
        assert [c["id"] for c in out["cues"]] == ["a"]
        assert "legacy_music_hint" not in out
