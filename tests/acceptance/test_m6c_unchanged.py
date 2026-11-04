"""m6c AC-12: behaviour that must not change. These pass before and after the work."""

from __future__ import annotations

import hashlib
import json

import pytest
from m6_helpers import build, get_asm, reel_world, wait_preview
from rf_helpers import run_async
from story_helpers import STORY_YAML


def _plain_edl():
    from reelforge.assembly.edl import Edl, EdlShot

    return Edl(
        project_id="p",
        video=[EdlShot(scene_id="s1", artifact="v", source_duration_s=20.0, in_s=0.0, out_s=20.0)],
        dialogue=[],
        captions=[],
    )


COMMERCIAL = ("MIT", "Apache-2.0", "BSD-2-Clause", "BSD-3-Clause", "ISC", "CC0-1.0", "Unlicense")


def test_a_story_with_only_the_old_music_block_still_loads():
    from reelforge.story.yamlio import parse_story

    story = parse_story(STORY_YAML)
    assert story.music is not None and story.music.track == "festive_dhol_01"
    assert getattr(story, "audio", None) is None


def test_an_edl_without_audio_keeps_its_old_hash_and_file_shape(tmp_path):
    from reelforge.assembly.edl import edl_hash, load_edl, save_edl

    edl = _plain_edl()
    dumped = {k: v for k, v in edl.model_dump(mode="json").items() if k not in ("audio", "mix")}
    expected = hashlib.sha256(
        json.dumps(dumped, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
    ).hexdigest()
    assert edl_hash(edl) == expected
    path = tmp_path / "edl.json"
    save_edl(edl, path)
    saved = json.loads(path.read_text())
    assert "audio" not in saved and "mix" not in saved
    assert load_edl(path) == edl


def test_the_mix_graph_without_cues_is_exactly_the_dialogue_only_graph():
    from reelforge.assembly.filtergraph import build_mix_graph

    assert build_mix_graph(_plain_edl()).to_script() == (
        "[0:a]apad=whole_dur=20,atrim=duration=20,"
        "aformat=sample_fmts=fltp:sample_rates=48000:channel_layouts=stereo[mix]"
    )


def test_the_mock_audio_task_without_a_duration_param_still_writes_one_second(tmp_path):
    from reelforge.adapters.base import CancelToken, TaskSpec
    from reelforge.adapters.mock import MockAdapter
    from reelforge.models_registry import ModelEntry, ModelRegistry
    from m4_helpers import read_wav

    entry = ModelEntry(key="tts", id="test-org/tts", revision="r1", license="MIT")
    adapter = MockAdapter(ModelRegistry([entry]), default_timeout_s=30.0, sample_interval_s=0.1)
    task = TaskSpec(kind="audio", prompt="hello", seed=1, params={}, model=entry)
    out = tmp_path / "o"
    out.mkdir()
    files = run_async(adapter.run(task, out, lambda pct, msg: None, CancelToken()))
    samples, rate, _, _ = read_wav(files[0].path)
    assert len(samples) / rate == pytest.approx(1.0, abs=0.01)
    hooked = TaskSpec(kind="audio", prompt="hello", seed=1, params={"mock": {"duration_s": 1.5}}, model=entry)
    out2 = tmp_path / "o2"
    out2.mkdir()
    files = run_async(adapter.run(hooked, out2, lambda pct, msg: None, CancelToken()))
    samples, rate, _, _ = read_wav(files[0].path)
    assert len(samples) / rate == pytest.approx(1.5, abs=0.01)


def test_a_reel_without_cues_adds_no_audio_fields_to_the_assembly_response(tmp_path):
    with reel_world(tmp_path) as (w, pid):
        build(w, pid)
        wait_preview(w, pid)
        asm = get_asm(w, pid)
        assert "audio_stale" not in asm and "audio_skipped" not in asm


def _toml(tmp_path, key: str, licence: str):
    from reelforge.config import PACKAGED_MODELS

    text = PACKAGED_MODELS.read_text()
    p = tmp_path / "models.toml"
    p.write_text(
        text + f'\n[models.{key}]\nid = "test-org/audio-x"\nrevision = "r1"\nlicense = "{licence}"\n'
        'license_url = "https://example.invalid/l"\n'
    )
    return p


@pytest.mark.parametrize("licence", ["MIT", "apache-2.0", "BSD-3-Clause", "CC0-1.0"])
def test_an_audio_model_with_a_commercial_licence_loads(tmp_path, licence):
    from reelforge.models_registry import load_models

    reg = load_models(_toml(tmp_path, "audio_music", licence))
    assert reg.get("audio_music").license == licence


def test_non_audio_models_are_not_held_to_the_audio_rule(tmp_path):
    from reelforge.models_registry import load_models

    reg = load_models(_toml(tmp_path, "other_thing", "CC-BY-NC-4.0"))
    assert reg.get("other_thing").license == "CC-BY-NC-4.0"


def test_the_packaged_models_toml_loads_with_only_commercial_audio_models():
    from reelforge.config import PACKAGED_MODELS
    from reelforge.models_registry import load_models

    reg = load_models(PACKAGED_MODELS)
    for e in reg.entries():
        if e.key.startswith("audio_"):
            assert e.license.lower() in {c.lower() for c in COMMERCIAL}, e



