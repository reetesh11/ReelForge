from typing import Literal

import pytest

from reelforge.voice.mapping import EmotionRule, KokoroAge, Mapping, PostSettings
from reelforge.voice.plan import plan_line


def _rule(
    tags, scale, pitch="", position: Literal["prefix", "suffix"] = "prefix", semitones=0.0, gen=None
):
    return EmotionRule(tags, position, pitch, scale, gen or {}, PostSettings(semitones=semitones))


MAPPING = Mapping(
    phrase_gap_ms=150,
    emotions={
        "happy": _rule(["[laughter]"], 0.9, "high pitch"),
        "sad": _rule(["[sigh]"], 1.25, "low pitch", gen={"guidance_scale": 2.0}),
        "fear": _rule(["[surprise-ah]"], 0.8, "high pitch", position="suffix"),
        "anger": _rule([], 0.95, "low pitch"),
    },
    kokoro={"elderly": KokoroAge(["hm_omega"], -1.0)},
)


def _plan(raw, emotion=None, **kw):
    args = {"mapping": MAPPING, "voice_model": "omnivoice", "speed": 1.0, "age": None}
    return plan_line(raw, emotion, **{**args, **kw})


def test_plain_line_is_one_default_phrase():
    p = _plan("Arre  Aloo")
    assert len(p.phrases) == 1 and p.is_default and p.gap_ms is None and not p.records_phrases
    ph = p.phrases[0]
    assert ph.model_text == "Arre  Aloo" and ph.instruct is None and ph.duration_factor == 1.0


def test_picker_emotion_overrides_markup_and_makes_one_phrase():
    p = _plan("<happy>Wah</happy> <fear>Arre</fear>", "sad")
    assert [x.emotion for x in p.phrases] == ["sad"] and p.gap_ms is None
    assert p.phrases[0].model_text == "[sigh] Wah Arre"
    assert p.records_phrases


def test_two_marked_phrases_carry_the_gap_and_their_own_values():
    p = _plan("<happy>Wah</happy> <fear>Arre</fear>")
    assert [x.emotion for x in p.phrases] == ["happy", "fear"] and p.gap_ms == 150
    assert p.phrases[1].model_text == "Arre [surprise-ah]"  # suffix position
    assert _plan("<happy>Wah</happy> <fear>Arre</fear>", gap_ms=400).gap_ms == 400


def test_unmarked_part_is_a_neutral_phrase():
    p = _plan("Tum kahan? <sad>Akela</sad>")
    assert [x.emotion for x in p.phrases] == [None, "sad"]
    assert p.phrases[0].tags == [] and p.phrases[0].duration_scale == 1.0


def test_speed_divides_the_duration_scale():
    p = _plan("Arre", "sad", speed=0.8)
    assert p.phrases[0].duration_factor == pytest.approx(1.25 / 0.8, abs=1e-4)


def test_instruct_joins_pitch_and_age_band_once_each():
    assert _plan("Arre", "sad", age=67).phrases[0].instruct == "low pitch, elderly"
    assert _plan("Arre", age=15).phrases[0].instruct == "teenager"
    assert _plan("Arre", "anger").phrases[0].instruct == "low pitch"


def test_clip_marks_the_reference_per_phrase():
    p = _plan("Arre <sad>Akela</sad>", has_clip=lambda e: e == "sad")
    assert [x.reference for x in p.phrases] == ["neutral", "emotion"]


def test_kokoro_applies_no_emotion_but_keeps_the_request_and_age_shift():
    p = _plan("<sad>[sigh] Arre</sad>", "sad", voice_model="kokoro", age=70)
    assert not p.emotion_applied and p.requested and not p.is_default
    ph = p.phrases[0]
    assert ph.model_text == "Arre" and ph.instruct is None and ph.duration_factor == 1.0
    assert ph.post.semitones == -1.0 and ph.emotion is None


def test_recorded_shape_has_post_without_tempo():
    rec = _plan("Arre", "sad").phrases[0].recorded()
    assert rec["post"] == {"semitones": 0.0, "gain_db": 0.0, "pause_s": 0.0}
    assert rec["generation"] == {"guidance_scale": 2.0} and rec["reference"] == "neutral"
