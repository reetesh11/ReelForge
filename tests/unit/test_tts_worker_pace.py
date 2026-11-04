"""Pace in the worker: length target from `duration_scale / target_speed`, and its limits."""

import json
import sys
import types

import numpy as np
import pytest

from reelforge.adapters import tts_worker
from reelforge.adapters.tts_worker import check_target, duration_factor, run_batch

TEXT = "ek do teen char paanch"


def _line(i="l", **over):
    return {
        "id": i, "text": TEXT, "model": "m/a", "voice": None, "ref_audio": None, "ref_text": None,
        "speed": 1.0, "lang": "hi", **over,
    }  # fmt: skip


def _run(tmp_path, *lines):
    events: list[dict] = []
    run_batch(list(lines), tmp_path, backend="mock", emit=events.append)
    return {e["id"]: e for e in events}


def test_factor_is_scale_over_target_speed():
    assert duration_factor(_line()) == 1.0
    assert duration_factor(_line(duration_scale=1.25, target_speed=0.8)) == pytest.approx(1.5625)


def test_length_follows_the_factor_and_neutral_rows_are_untouched(tmp_path):
    ev = _run(
        tmp_path,
        _line("a"),
        _line("b", duration_scale=1.0, target_speed=1.0, instruct=None, gen={}),
        _line("c", duration_scale=2.0, target_speed=1.0),
        _line("d", target_speed=0.5),
    )
    assert ev["a"]["duration_s"] == ev["b"]["duration_s"]
    assert (tmp_path / "a.wav").read_bytes() == (tmp_path / "b.wav").read_bytes()
    assert "duration_requested_s" not in ev["a"] and "duration_requested_s" not in ev["b"]
    base_tone = ev["a"]["duration_s"] - 0.6
    for key in ("c", "d"):
        assert ev[key]["duration_s"] - 0.6 == pytest.approx(2 * base_tone, rel=0.02)
        assert ev[key]["duration_requested_s"] == pytest.approx(2 * base_tone, rel=0.02)


@pytest.mark.parametrize("scale", [0.01, 100.0])
def test_target_outside_the_model_limits_fails_that_row_only(tmp_path, scale):
    ev = _run(tmp_path, _line("bad", duration_scale=scale), _line("ok"))
    assert "outside what the model accepts (0.3 to 60 s)" in ev["bad"]["error"]
    assert "error" not in ev["ok"]


def test_check_target_message_names_the_value():
    with pytest.raises(ValueError, match=r"Duration target 61 s is outside"):
        check_target(61.0)


class _Result:
    def __init__(self, audio):
        self.audio = audio


class _Model:
    sample_rate = 24000

    def __init__(self, calls):
        self.calls = calls

    def generate(self, **kwargs):
        self.calls.append(kwargs)
        yield _Result(np.zeros(2400, dtype="float32"))


class _Estimator:
    def estimate_duration(self, text, ref_text, ref_duration):
        return 100.0  # tokens


@pytest.fixture
def fake_omnivoice(monkeypatch):
    calls: list[dict] = []
    names = [
        "mlx_audio",
        "mlx_audio.tts",
        "mlx_audio.tts.utils",
        "mlx_audio.tts.models",
        "mlx_audio.tts.models.omnivoice",
        "mlx_audio.tts.models.omnivoice.duration",
    ]
    for n in names:
        monkeypatch.setitem(sys.modules, n, types.ModuleType(n))
    sys.modules["mlx_audio.tts.utils"].load_model = lambda _id: _Model(calls)  # type: ignore[attr-defined]
    sys.modules["mlx_audio.tts.models.omnivoice.duration"].RuleDurationEstimator = _Estimator  # type: ignore[attr-defined]
    return calls


def test_real_omnivoice_gets_duration_instruct_and_generation_settings(fake_omnivoice):
    synth = tts_worker._real_loader("mlx-community/OmniVoice-bfloat16")
    out = synth(
        {
            "text": "x",
            "voice": "A warm voice",
            "instruct": "low pitch, elderly",
            "speed": 1.0,
            "duration_scale": 1.25,
            "target_speed": 0.8,
            "gen": {"guidance_scale": 2.0},
        }  # fmt: skip
    )
    kw = fake_omnivoice[0]
    assert kw["instruct"] == "A warm voice, low pitch, elderly" and kw["guidance_scale"] == 2.0
    base = int(100 * 1.15) / (24000 / 960)
    assert kw["duration_s"] == pytest.approx(base * 1.25 / 0.8) and "speed" not in kw
    assert out[2] == kw["duration_s"]


def test_real_omnivoice_at_factor_one_passes_no_duration(fake_omnivoice):
    synth = tts_worker._real_loader("mlx-community/OmniVoice-bfloat16")
    out = synth({"text": "x", "voice": None, "speed": 1.0})
    assert "duration_s" not in fake_omnivoice[0] and len(out) == 2


def test_batch_file_round_trip_keeps_new_keys(tmp_path):
    batch = tmp_path / "b.jsonl"
    batch.write_text(json.dumps(_line(duration_scale=1.5, target_speed=1.0)) + "\n")
    assert (
        tts_worker.main(["--batch", str(batch), "--out-dir", str(tmp_path), "--backend", "mock"])
        == 0
    )
