from reelforge.voice import effective
from reelforge.voice.mapping import EmotionRule, Mapping, PostSettings
from reelforge.voice.plan import plan_line


def _mapping(scale=1.25, gap=150):
    rule = EmotionRule(["[sigh]"], "prefix", "low pitch", scale, {}, PostSettings(-2.0, -3.0, 0.0))
    other = EmotionRule([], "prefix", "", 1.0, {}, PostSettings())
    return Mapping(gap, {"happy": other, "sad": rule, "fear": other, "anger": other}, {})


def _plan(raw="Arre", emotion=None, mapping=None, **kw):
    args = {"voice_model": "omnivoice", "speed": 1.0, "age": None, "gap_ms": None}
    return plan_line(raw, emotion, mapping=mapping or _mapping(), **{**args, **kw})


def _params(plan, source="tts", **over):
    out = {"text": "Arre", "speed": plan.speed, "voice": {}, "source": source}
    if plan.age_band:
        out["age_band"] = plan.age_band
    if plan.gap_ms is not None:
        out["gap_ms"] = plan.gap_ms
    if plan.records_phrases:
        out["phrases"] = [
            {**p.recorded(), "duration_requested_s": None, "reference_artifact_id": None}
            for p in plan.phrases
        ]
    return {**out, **over}


def test_default_delivery_has_no_effective_and_no_settings():
    plan = _plan()
    assert effective.effective_body(plan) is None
    assert effective.take_settings(_params(plan)) is None


def test_effective_lists_phrases_with_factor_and_label():
    plan = _plan("Arre", "sad", speed=0.8, age=67)
    body = effective.effective_body(plan)
    assert body and body["emotion_applied"] is True and body["age_band"] == "elderly"
    ph = body["phrases"][0]
    assert (
        ph["duration_factor"] == round(1.25 / 0.8, 4)
        and ph["reference_label"] == "Neutral reference"
    )
    assert ph["post"] == {"semitones": -2.0, "gain_db": -3.0, "pause_s": 0.0}


def test_recorded_settings_match_the_plan_that_made_them():
    plan = _plan("Arre", "sad")
    rec = effective.take_settings(_params(plan, duration_requested_s=2.0))
    assert rec and rec["duration_requested_s"] == 2.0
    assert not effective.settings_changed(plan, effective.effective_body(plan), rec)
    other = _plan("Arre", "sad", speed=0.8)
    assert effective.settings_changed(other, effective.effective_body(other), rec)


def test_mapping_edit_makes_an_emotional_take_stale_but_not_a_plain_one():
    plan = _plan("Arre", "sad")
    params = _params(plan)
    assert not effective.values_stale(params, plan, _mapping(), 150, {})
    assert effective.values_stale(params, plan, _mapping(scale=1.5), 150, {})
    plain = _plan()
    assert not effective.values_stale(_params(plain), plain, _mapping(scale=9.0), 999, {})


def test_gap_only_matters_for_multi_phrase_takes():
    plan = _plan("<happy>a</happy> <sad>b</sad>")
    params = _params(plan)
    assert not effective.values_stale(params, plan, _mapping(), 150, {})
    assert effective.values_stale(params, plan, _mapping(), 400, {})


def test_removed_or_replaced_clip_makes_a_take_stale():
    plan = _plan("Arre", "sad", has_clip=lambda e: True)
    params = _params(plan)
    params["phrases"][0]["reference_artifact_id"] = "clip1"
    assert not effective.values_stale(params, plan, _mapping(), 150, {"sad": "clip1"})
    assert effective.values_stale(params, plan, _mapping(), 150, {})
    assert effective.values_stale(params, plan, _mapping(), 150, {"sad": "clip2"})


def test_age_band_change_and_uploaded_recordings():
    plan = _plan(age=67)
    params = _params(plan)
    assert not effective.values_stale(params, plan, _mapping(), 150, {})
    assert effective.values_stale(params, _plan(age=30), _mapping(), 150, {})
    assert not effective.values_stale({**params, "source": "upload"}, _plan(), _mapping(), 150, {})
