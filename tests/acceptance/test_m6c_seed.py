"""m6c R11, AC-9: cues suggested from the storyline; nothing generates until approved."""

from __future__ import annotations

import pytest
from m6c_helpers import at, audio_url, cue, get_audio, jobs_of_type, story_with_audio
from rf_helpers import create_project, make_client
from story_helpers import new_ctx, reply, story_dict, structure, versions

DIRECTIONS = [
    ("TRACK 2 kicks in as the tomato storms off", "music"),
    ("a gong slam when the box opens", "sfx"),
    ("drum roll before the reveal", "sfx"),
    ("a ceramic crash and the plate breaks", "sfx"),
    ("the packaging crinkle as she opens it", "sfx"),
    ("a loud crunch on the first bite", "sfx"),
    ("complete silence for a beat", "silence"),
    ("wedding hall ambience under everything", "ambience"),
]


def _story(**over):
    from reelforge.story.yamlio import parse_story

    return parse_story(story_with_audio(None, **over))


@pytest.mark.parametrize("text, kind", DIRECTIONS)
def test_a_direction_in_the_text_becomes_a_suggested_cue_of_the_right_kind(text, kind):
    from reelforge.audio.seed import suggest_cues
    from reelforge.story.yamlio import parse_story

    story = _story()
    cues = suggest_cues(text, story)
    assert cues and all(c.state == "suggested" for c in cues)
    assert kind in {c.kind for c in cues}
    assert len({c.id for c in cues}) == len(cues)
    # every suggestion is a valid cue in this story
    data = [c.model_dump(mode="json", exclude_none=True) for c in cues]
    assert parse_story(story_with_audio(data)).audio is not None


def test_text_without_sound_directions_gives_no_cues():
    from reelforge.audio.seed import suggest_cues

    assert suggest_cues("Aloo walks to the market and buys three tomatoes.", _story()) == []


def test_merge_never_removes_or_edits_and_skips_duplicates():
    from reelforge.audio.seed import merge_suggestions
    from reelforge.story.schema import Cue

    def mk(id_, kind, scene, prompt, **kw):
        return Cue.model_validate(cue(id_, kind, at(scene), duration=1.0, prompt=prompt, **kw))

    existing = [mk("gong", "sfx", "s2", "gong slam edited by me"), mk("bed", "music", "s1", "festive")]
    new = [
        mk("gong", "sfx", "s3", "different", state="suggested"),  # same id
        mk("other", "music", "s1", "festive", state="suggested"),  # same kind, scene, prompt as bed
        mk("fresh", "sfx", "s4", "crunch", state="suggested"),
    ]
    merged = merge_suggestions(existing, new)
    assert merged[:2] == existing
    assert [c.id for c in merged] == ["gong", "bed", "fresh"]
    assert merged[2].state == "suggested"
    assert merge_suggestions(merged, new) == merged


def _storyline():
    return "A tomato and a potato at a wedding. TRACK 2 kicks in. A gong slam. Then complete silence."


def test_structuring_adds_suggested_cues_and_starts_no_generation(tmp_path):
    from reelforge.adapters.mock_llm import MockLlm

    llm = MockLlm(responses=[reply(story_dict())])
    ctx = new_ctx(tmp_path, llm=llm)
    with make_client(ctx) as client:
        pid = create_project(client)["id"]
        job = structure(client, ctx, pid, storyline=_storyline())
        assert job.status == "succeeded", job.error
        cues = get_audio(client, pid)["cues"]
        assert cues and all(c["state"] == "suggested" for c in cues)
        assert {"music", "sfx", "silence"} <= {c["kind"] for c in cues}
        assert jobs_of_type(ctx, pid, "gen_audio_cue") == []
        r = client.post(audio_url(pid, f"/cues/{cues[0]['id']}:generate"))
        assert r.status_code == 409 and r.json()["detail"] == "Approve this cue before generating it."
        assert jobs_of_type(ctx, pid, "gen_audio_cue") == []


def test_structuring_again_keeps_approved_and_edited_cues_and_adds_no_duplicates(tmp_path):
    from reelforge.adapters.mock_llm import MockLlm

    llm = MockLlm(responses=[reply(story_dict())])
    ctx = new_ctx(tmp_path, llm=llm)
    with make_client(ctx) as client:
        pid = create_project(client)["id"]
        assert structure(client, ctx, pid, storyline=_storyline()).status == "succeeded"
        first = get_audio(client, pid)["cues"]
        keep = next(c for c in first if c["kind"] != "silence")["id"]
        assert client.post(audio_url(pid, f"/cues/{keep}:approve")).status_code == 200
        body = next(c for c in get_audio(client, pid)["cues"] if c["id"] == keep)
        edited = {
            k: body[k]
            for k in ("id", "kind", "start", "end", "duration", "source", "gain_db", "fade_in_s", "fade_out_s", "duck")
            if body.get(k) is not None
        }
        edited["prompt"] = "my own prompt"
        assert client.put(audio_url(pid, f"/cues/{keep}"), json=edited).status_code == 200
        assert structure(client, ctx, pid, storyline=_storyline()).status == "succeeded"
        again = get_audio(client, pid)["cues"]
        assert [c["id"] for c in again] == [c["id"] for c in first]
        kept = next(c for c in again if c["id"] == keep)
        assert kept["state"] != "suggested" and kept["prompt"] == "my own prompt"
        assert jobs_of_type(ctx, pid, "gen_audio_cue") == []


def test_a_carried_over_cue_that_no_longer_validates_fails_the_job_and_saves_nothing(tmp_path):
    from reelforge.adapters.mock_llm import MockLlm

    four = story_dict(4)
    llm = MockLlm(responses=[reply(story_dict()), reply(four)])
    ctx = new_ctx(tmp_path, llm=llm)
    with make_client(ctx) as client:
        pid = create_project(client)["id"]
        assert structure(client, ctx, pid, storyline="Plain story with no sound notes.").status == "succeeded"
        late = cue("late", "sfx", at("s5"), duration=1.0)
        assert client.post(audio_url(pid, "/cues"), json=late).status_code == 201
        before = len(versions(client, pid))
        job = structure(client, ctx, pid, storyline="Plain story with no sound notes.")
        assert job.status == "failed"
        assert 'Cue "late": unknown scene "s5".' in job.error
        assert len(versions(client, pid)) == before
        assert [c["id"] for c in get_audio(client, pid)["cues"]] == ["late"]
