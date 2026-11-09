"""m6c R12, R13, AC-10: audio model licences in models.toml, credits and the export licence check."""

from __future__ import annotations

import pytest
from m6_helpers import build, export, get_asm, wait_preview
from m6c_helpers import FREQ, at, audio_reel_world, cue, generated, upload_cue_file, wav_bytes

COMMERCIAL = ("MIT", "Apache-2.0", "BSD-2-Clause", "BSD-3-Clause", "ISC", "CC0-1.0", "Unlicense")


def _toml(tmp_path, key: str, licence: str):
    from reelforge.config import PACKAGED_MODELS

    text = PACKAGED_MODELS.read_text()
    p = tmp_path / "models.toml"
    p.write_text(
        text + f'\n[models.{key}]\nid = "test-org/audio-x"\nrevision = "r1"\nlicense = "{licence}"\n'
        'license_url = "https://example.invalid/l"\n'
    )
    return p


def test_the_commercial_licence_list_is_the_documented_one():
    from reelforge.models_registry import COMMERCIAL_LICENCES

    assert tuple(COMMERCIAL_LICENCES) == COMMERCIAL


@pytest.mark.parametrize("licence", ["CC-BY-NC-4.0", "Non-Commercial Research", "", "GPL-3.0"])
def test_an_audio_model_with_another_or_empty_licence_is_rejected_at_load(tmp_path, licence):
    from reelforge.models_registry import ModelLicenceError, load_models

    with pytest.raises(ModelLicenceError) as ei:
        load_models(_toml(tmp_path, "audio_sfx", licence))
    assert isinstance(ei.value, ValueError)


def test_check_audio_licences_and_a_directly_built_registry():
    from reelforge.models_registry import ModelEntry, ModelLicenceError, ModelRegistry, check_audio_licences

    ok = ModelEntry(key="audio_music", id="a", revision="r", license="Apache-2.0")
    bad = ModelEntry(key="audio_sfx", id="b", revision="r", license="CC-BY-NC-4.0")
    skip = ModelEntry(key="image", id="c", revision="r", license="FLUX Non-Commercial")
    check_audio_licences([ok, skip])
    with pytest.raises(ModelLicenceError):
        check_audio_licences([ok, bad])
    assert ModelRegistry([ok, bad]).get("audio_sfx") is bad  # building it does not run the check


def test_max_seconds_is_optional_and_must_be_positive():
    from pydantic import ValidationError
    from reelforge.models_registry import ModelEntry

    assert ModelEntry(key="k", id="i", revision="r").max_seconds is None
    assert ModelEntry(key="k", id="i", revision="r", max_seconds=30.0).max_seconds == 30.0
    for bad in (0, -5.0):
        with pytest.raises(ValidationError):
            ModelEntry(key="k", id="i", revision="r", max_seconds=bad)


def _cues():
    return [
        cue("m1", "music", at("s1"), duration=3.0, prompt="festive"),
        cue("f1", "sfx", at("s3"), duration=2.0, source="file"),
        cue("hush", "silence", at("s4"), duration=1.0),
    ]


def _warn_audio(warnings):
    return [x for x in warnings if "cue_id" in x]


def test_credits_list_every_generated_and_uploaded_cue(tmp_path):
    from reelforge.assembly.build import build_edl
    from reelforge.assembly.publish import collect_credits

    with audio_reel_world(tmp_path, _cues()) as (w, pid):
        generated(w.client, w.ctx, pid, "m1")
        r = upload_cue_file(w.client, pid, "f1", wav_bytes(1.0, rate=24000), name="gong.wav", note="CC0 from me")
        assert r.status_code == 201, r.text
        edl = build_edl(w.ctx, pid)
        assert [a.cue_id for a in edl.audio] == ["m1", "f1", "hush"]
        credits = collect_credits(w.ctx, pid, edl)
        by = {c["cue_id"]: c for c in credits if "cue_id" in c}
        assert set(by) == {"m1", "f1"}, "silence has no credit"
        assert set(by["m1"]) == {"cue_id", "kind", "model", "version", "licence"}
        assert by["m1"]["kind"] == "music" and by["m1"]["licence"].lower() in {c.lower() for c in COMMERCIAL}
        assert by["m1"]["model"] and by["m1"]["version"]
        assert by["f1"] == {"cue_id": "f1", "kind": "sfx", "file_name": "gong.wav", "licence": "CC0 from me"}
        old = [c for c in credits if "cue_id" not in c]
        assert old and all(set(c) == {"model", "version", "licence"} for c in old)


def test_an_upload_without_a_licence_note_triggers_the_export_licence_check(tmp_path):
    from reelforge.assembly.build import build_edl
    from reelforge.assembly.publish import collect_credits, licence_warnings

    with audio_reel_world(tmp_path, _cues()) as (w, pid):
        generated(w.client, w.ctx, pid, "m1")
        assert upload_cue_file(w.client, pid, "f1", wav_bytes(1.0, rate=24000), name="gong.wav").status_code == 201
        build(w, pid)
        wait_preview(w, pid)
        warn = _warn_audio(licence_warnings(collect_credits(w.ctx, pid, build_edl(w.ctx, pid))))
        assert warn == [{"cue_id": "f1", "kind": "sfx", "file_name": "gong.wav", "licence": ""}]
        r = export(w, pid, accept=False)
        assert r.status_code == 409 and r.json()["detail"] == "Licence check before export"
        assert warn[0] in r.json()["licence_warnings"]
        assert warn[0] in get_asm(w, pid)["licence_warnings"]
        # a note clears it
        assert upload_cue_file(w.client, pid, "f1", wav_bytes(1.0, rate=24000), name="gong.wav", note="mine").status_code == 201
        assert _warn_audio(licence_warnings(collect_credits(w.ctx, pid, build_edl(w.ctx, pid)))) == []


def test_a_generated_cue_from_a_non_commercial_model_triggers_the_licence_check(tmp_path):
    from reelforge.assembly.build import build_edl
    from reelforge.assembly.publish import collect_credits, licence_warnings
    from reelforge.models_registry import ModelEntry, ModelRegistry
    from m6c_helpers import take_artifacts

    with audio_reel_world(tmp_path, _cues()) as (w, pid):
        generated(w.client, w.ctx, pid, "m1")
        (art,) = take_artifacts(w.ctx, pid, "m1")
        entries = [e for e in w.ctx.registry.entries() if e.key != art.model_key]
        entries.append(ModelEntry(key=art.model_key, id="test-org/nc-music", revision="v9", license="CC-BY-NC-4.0"))
        w.ctx.registry = ModelRegistry(entries)
        credits = collect_credits(w.ctx, pid, build_edl(w.ctx, pid))
        mine = next(c for c in credits if c.get("cue_id") == "m1")
        assert mine["model"] == "test-org/nc-music" and mine["version"] == "v9" and mine["licence"] == "CC-BY-NC-4.0"
        assert mine in licence_warnings(credits)
        r = export(w, pid, accept=False)
        assert r.status_code == 409 and mine in r.json()["licence_warnings"]


_ = FREQ
