"""m6 R2-R6, AC-1 to AC-5, AC-7: the render engine on mock media."""

from __future__ import annotations

import json

import pytest
from m6_helpers import (
    FINAL_STEPS,
    PREVIEW_STEPS,
    Kill,
    first_sound_s,
    loudness,
    max_volume_db,
    probe,
    reel_world,
    render,
    small_edl,
    voice_take_id,
    take_id,
)


def _full_edl(w, pid):
    from reelforge.assembly.build import build_edl

    return build_edl(w.ctx, pid)


def test_preview_is_540x960_with_a_filtergraph_next_to_it(tmp_path):
    with reel_world(tmp_path) as (w, pid):
        edl = _full_edl(w, pid)
        out = tmp_path / "pv"
        res = render(w, edl, out, "preview")
        assert res.output == out / "preview.mp4" and res.output.is_file()
        assert res.filtergraph == out / "preview.filtergraph.txt"
        script = res.filtergraph.read_text()
        assert script.strip() and "[" in script and "=" in script
        p = probe(res.output)
        assert (p["video"]["width"], p["video"]["height"]) == (540, 960)
        assert p["video"]["codec_name"] == "h264" and p["audio"]["codec_name"] == "aac"
        assert float(p["format"]["duration"]) == pytest.approx(edl.total_duration_s, abs=0.05)


def test_final_matches_the_export_spec(tmp_path):
    """AC-1 (file properties) and R3: 1080x1920, 24 fps, High yuv420p, AAC 48 kHz stereo, faststart."""
    with reel_world(tmp_path) as (w, pid):
        edl = _full_edl(w, pid)
        res = render(w, edl, tmp_path / "fin", "final")
        assert res.output.name == "final.mp4" and res.filtergraph.name == "final.filtergraph.txt"
        assert res.filtergraph.read_text().strip()
        p = probe(res.output)
        v, a = p["video"], p["audio"]
        assert (v["width"], v["height"]) == (1080, 1920)
        assert v["codec_name"] == "h264" and v["profile"] == "High" and v["pix_fmt"] == "yuv420p"
        assert v["avg_frame_rate"] == "24/1" and v["r_frame_rate"] == "24/1"
        assert a["codec_name"] == "aac" and a["sample_rate"] == "48000" and a["channels"] == 2
        assert float(p["format"]["duration"]) == pytest.approx(edl.total_duration_s, abs=0.05)
        assert int(v["nb_frames"]) == pytest.approx(edl.total_frames, abs=1)
        data = res.output.read_bytes()
        assert 0 <= data.find(b"moov") < data.find(b"mdat")


def test_loudness_is_normalised(tmp_path):
    """AC-2: about -14 LUFS integrated, true peak at most -1 dBTP."""
    with reel_world(tmp_path) as (w, pid):
        res = render(w, _full_edl(w, pid), tmp_path / "fin", "final")
        lufs, peak = loudness(res.output)
        assert lufs == pytest.approx(-14.0, abs=1.5)
        assert peak <= -0.9


def test_progress_and_state_record_every_step(tmp_path):
    with reel_world(tmp_path) as (w, pid):
        edl = small_edl(_full_edl(w, pid))
        calls: list[tuple[float, str]] = []
        out = tmp_path / "pv"
        res = render(w, edl, out, "preview", progress=lambda pct, msg: calls.append((pct, msg)))
        assert [m for _, m in calls] == [f"{n} ({i} of 8)" for i, n in enumerate(PREVIEW_STEPS, 1)]
        assert [p for p, _ in calls] == pytest.approx([i / 8 * 100 for i in range(8)])
        state = json.loads((out / "state.json").read_text())
        from reelforge.assembly.edl import edl_hash

        assert state["edl_hash"] == edl_hash(edl) and state["profile"] == "preview"
        assert state["steps"] == {n: {"done": True, "runs": 1} for n in PREVIEW_STEPS}
        assert res.step_runs == {n: 1 for n in PREVIEW_STEPS}
        assert not list(out.rglob("*.part"))


def test_final_profile_also_runs_the_eight_render_steps(tmp_path):
    with reel_world(tmp_path) as (w, pid):
        res = render(w, small_edl(_full_edl(w, pid)), tmp_path / "fin", "final")
        assert set(res.step_runs) == set(PREVIEW_STEPS) and set(PREVIEW_STEPS) < set(FINAL_STEPS)


def test_rerendering_the_same_edl_runs_nothing_again(tmp_path):
    with reel_world(tmp_path) as (w, pid):
        edl = small_edl(_full_edl(w, pid))
        out = tmp_path / "pv"
        render(w, edl, out, "preview")
        res = render(w, edl, out, "preview")
        assert res.step_runs == {n: 1 for n in PREVIEW_STEPS} and res.output.is_file()


def test_a_changed_edl_restarts_the_folder(tmp_path):
    from reelforge.assembly.edl import edl_hash

    with reel_world(tmp_path) as (w, pid):
        edl = small_edl(_full_edl(w, pid))
        out = tmp_path / "pv"
        first = render(w, edl, out, "preview")
        d1 = float(probe(first.output)["format"]["duration"])
        shorter = edl.video[0].model_copy(update={"out_s": edl.video[0].out_s - 0.5})
        edl2 = edl.model_copy(update={"video": [shorter, *edl.video[1:]]})
        res = render(w, edl2, out, "preview")
        assert json.loads((out / "state.json").read_text())["edl_hash"] == edl_hash(edl2)
        assert float(probe(res.output)["format"]["duration"]) == pytest.approx(d1 - 0.5, abs=0.06)
        assert res.step_runs == {n: 1 for n in PREVIEW_STEPS}


@pytest.mark.parametrize("step", PREVIEW_STEPS)
def test_killed_before_a_step_resumes_without_rerunning_done_steps(tmp_path, step):
    """AC-7 / R5."""
    from reelforge.assembly.render import RenderHooks

    with reel_world(tmp_path) as (w, pid):
        edl = small_edl(_full_edl(w, pid))
        out = tmp_path / "pv"

        def before(name: str) -> None:
            if name == step:
                raise Kill()

        with pytest.raises(Kill):
            render(w, edl, out, "preview", hooks=RenderHooks(before_step=before))
        k = PREVIEW_STEPS.index(step)
        state = json.loads((out / "state.json").read_text()) if (out / "state.json").exists() else {}
        done = {n for n, v in state.get("steps", {}).items() if v["done"]}
        assert done == set(PREVIEW_STEPS[:k])
        res = render(w, edl, out, "preview")
        assert res.step_runs == {n: 1 for n in PREVIEW_STEPS}
        assert res.output.is_file() and not list(out.rglob("*.part"))


@pytest.mark.parametrize("step", PREVIEW_STEPS)
def test_killed_after_a_step_keeps_that_step_done(tmp_path, step):
    from reelforge.assembly.render import RenderHooks

    with reel_world(tmp_path) as (w, pid):
        edl = small_edl(_full_edl(w, pid))
        out = tmp_path / "pv"

        def after(name: str) -> None:
            if name == step:
                raise Kill()

        with pytest.raises(Kill):
            render(w, edl, out, "preview", hooks=RenderHooks(after_step=after))
        k = PREVIEW_STEPS.index(step)
        state = json.loads((out / "state.json").read_text())
        assert {n for n, v in state["steps"].items() if v["done"]} == set(PREVIEW_STEPS[: k + 1])
        res = render(w, edl, out, "preview")
        assert res.step_runs == {n: 1 for n in PREVIEW_STEPS}


def test_dialogue_lands_at_its_offset_on_a_silent_shot(tmp_path):
    """AC-4: within one frame; the shot itself has no audio, which counts as silence."""
    from reelforge.assembly.edl import EdlDialogue

    with reel_world(tmp_path) as (w, pid):
        edl = _full_edl(w, pid)
        s3 = next(s for s in edl.video if s.scene_id == "s3")
        clip = next(d for d in edl.dialogue if d.scene_id == "s1")
        edl = edl.model_copy(
            update={
                "video": [s3],
                "captions": [],
                "dialogue": [
                    EdlDialogue(scene_id="s3", artifact=voice_take_id(w, pid, "s1"), offset_s=1.0,
                                duration_s=clip.duration_s)
                ],
            }
        )
        assert edl.video[0].artifact == take_id(w, pid, "s3")
        res = render(w, edl, tmp_path / "pv", "preview")
        assert first_sound_s(res.output) == pytest.approx(1.0, abs=1 / 24 + 0.02)


def test_shots_without_audio_become_silence_not_an_error(tmp_path):
    with reel_world(tmp_path) as (w, pid):
        edl = _full_edl(w, pid)
        s3 = next(s for s in edl.video if s.scene_id == "s3")
        edl = edl.model_copy(update={"video": [s3], "dialogue": [], "captions": []})
        res = render(w, edl, tmp_path / "pv", "preview")
        p = probe(res.output)
        assert p["audio"] is not None
        assert float(p["format"]["duration"]) == pytest.approx(edl.total_duration_s, abs=0.05)
        assert max_volume_db(res.output) <= -60.0


def test_captions_ass_is_written_and_burned_when_libass_exists(tmp_path):
    from reelforge.assembly.ffmpeg import has_filter

    with reel_world(tmp_path) as (w, pid):
        edl = small_edl(_full_edl(w, pid))
        out = tmp_path / "pv"
        res = render(w, edl, out, "preview")
        assert res.captions_burned is has_filter("subtitles")
        ass = (out / "captions.ass").read_text()
        assert "PlayResX: 1080" in ass
        assert all(word in ass for word in edl.captions[0].text.split())
        assert "\\k" in ass, "the proportional aligner times the words of a Bold pop line"


def test_a_failing_aligner_falls_back_to_line_timing(tmp_path):
    from reelforge.assembly.align import AlignmentError

    class Boom:
        async def align(self, audio, text, language):
            raise AlignmentError("no model")

    with reel_world(tmp_path) as (w, pid):
        w.ctx.aligner = Boom()
        edl = small_edl(_full_edl(w, pid))
        out = tmp_path / "pv"
        render(w, edl, out, "preview")
        ass = (out / "captions.ass").read_text()
        assert "\\k" not in ass and edl.captions[0].text in ass


def test_missing_shot_file_is_a_step_error(tmp_path):
    from reelforge.assembly.state import StepError
    from m5_helpers import art_path

    with reel_world(tmp_path) as (w, pid):
        edl = small_edl(_full_edl(w, pid))
        art_path(w, edl.video[1].artifact).unlink()
        with pytest.raises(StepError) as exc:
            render(w, edl, tmp_path / "pv", "preview")
        assert exc.value.step == "Preparing shots"
        assert exc.value.reason == "A shot file is missing: s2" == str(exc.value)


def test_filter_graph_script_serialisation():
    from reelforge.assembly.filtergraph import Chain, Filter, FilterGraph

    g = FilterGraph(
        [
            Chain(["0:v"], [Filter("scale", [1080, 1920]), Filter("format", {"pix_fmts": "yuv420p"})], ["v0"]),
            Chain(["v0", "v1"], [Filter("concat", {"n": 2, "v": 1, "a": 0})], ["out"]),
        ]
    )
    script = g.to_script()
    chains = script.split(";\n")
    assert len(chains) == 2
    assert chains[0] == "[0:v]scale=1080:1920,format=pix_fmts=yuv420p[v0]"
    assert chains[1].startswith("[v0][v1]concat=") and chains[1].endswith("[out]")
    assert "n=2" in chains[1] and "v=1" in chains[1] and "a=0" in chains[1]
