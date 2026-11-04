"""Credits, licence warnings and output verification."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from reelforge.assembly import ffmpeg, publish
from reelforge.assembly.edl import Edl, EdlShot
from reelforge.assembly.state import StepError


def test_licence_warnings_flag_empty_and_non_commercial() -> None:
    credits = [
        {"model": "a", "version": "1", "licence": "MIT"},
        {"model": "b", "version": "1", "licence": ""},
        {"model": "c", "version": "1", "licence": "Foo Non-Commercial License"},
        {"model": "d", "version": "1", "licence": "LTX-2 Community License"},
    ]
    assert [c["model"] for c in publish.licence_warnings(credits)] == ["b", "c"]


def _edl() -> Edl:
    shot = EdlShot(scene_id="s1", artifact="a", source_duration_s=2.0, in_s=0, out_s=2.0)
    return Edl(project_id="p", video=[shot], dialogue=[], captions=[])


def _info(**over: object) -> dict:
    video = {
        "codec_type": "video", "width": 1080, "height": 1920, "avg_frame_rate": "24/1",
    }  # fmt: skip
    audio = {"codec_type": "audio", "sample_rate": "48000", "channels": 2}
    info = {"streams": [video, audio], "format": {"duration": "2.0"}}
    info.update(over)
    return info


@pytest.mark.parametrize(
    "info, check",
    [
        (_info(format={"duration": "5.0"}), "length does not match the edit"),
        (
            _info(streams=[{"codec_type": "video", "width": 540, "height": 960,
                            "avg_frame_rate": "24/1"}]),
            "size is not 1080x1920",
        ),
        (
            _info(streams=[{"codec_type": "video", "width": 1080, "height": 1920,
                            "avg_frame_rate": "24/1"}]),
            "no audio stream",
        ),
        (
            _info(streams=[{"codec_type": "video", "width": 1080, "height": 1920,
                            "avg_frame_rate": "30/1"},
                           {"codec_type": "audio", "sample_rate": "48000", "channels": 2}]),
            "frame rate is not 24 fps",
        ),
    ],
)  # fmt: skip
def test_verify_names_the_failing_check(
    monkeypatch: pytest.MonkeyPatch, info: dict, check: str
) -> None:
    monkeypatch.setattr(ffmpeg, "probe", lambda path: info)
    with pytest.raises(StepError) as exc:
        publish.verify_output(Path("x.mp4"), _edl())
    assert exc.value.step == "Verifying" and check in str(exc.value)


def test_verify_accepts_a_good_file(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(ffmpeg, "probe", lambda path: _info())
    publish.verify_output(Path("x.mp4"), _edl())


def test_credits_are_one_per_model_and_include_align_for_real_aligner() -> None:
    from reelforge.assembly.align import MlxWhisperAligner
    from reelforge.models_registry import ModelEntry, ModelRegistry

    reg = ModelRegistry(
        [
            ModelEntry(key="video", id="v", revision="1", license="X"),
            ModelEntry(key="align", id="w", revision="2", license="MIT"),
        ]
    )
    ctx = SimpleNamespace(registry=reg, aligner=MlxWhisperAligner(SimpleNamespace()))  # type: ignore[arg-type]
    publish_keys = {"video"}
    ctx.session_factory = None  # not reached: _model_keys is patched
    orig = publish._model_keys
    publish._model_keys = lambda c, e: set(publish_keys)  # type: ignore[assignment]
    try:
        edl = _edl().model_copy(update={"captions": [SimpleNamespace(text="hi")]})
        out = publish.collect_credits(ctx, "p", edl)  # type: ignore[arg-type]
    finally:
        publish._model_keys = orig
    assert out == [
        {"model": "v", "version": "1", "licence": "X"},
        {"model": "w", "version": "2", "licence": "MIT"},
    ]
