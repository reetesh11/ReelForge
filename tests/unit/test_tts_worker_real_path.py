"""The real-model path of the worker, with a fake mlx-audio package (no model is loaded).

Found on the reference Mac: the stub-based tests could not see that running the worker as a
script put `adapters/` first on the import path, or that OmniVoice ignores a `voice` argument.
"""

import sys
import types
from pathlib import Path

import numpy as np
import pytest

from reelforge.adapters import tts_worker

HERE = Path(tts_worker.__file__).resolve().parent


class _Result:
    def __init__(self, audio):
        self.audio = audio


class _FakeModel:
    sample_rate = 24000

    def __init__(self, calls):
        self.calls = calls

    def generate(self, **kwargs):
        self.calls.append(kwargs)
        yield _Result(np.zeros(2400, dtype="float32"))


@pytest.fixture
def fake_mlx_audio(monkeypatch):
    calls: list[dict] = []
    package = types.ModuleType("mlx_audio")
    tts = types.ModuleType("mlx_audio.tts")
    utils = types.ModuleType("mlx_audio.tts.utils")
    utils.load_model = lambda _model_id: _FakeModel(calls)  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "mlx_audio", package)
    monkeypatch.setitem(sys.modules, "mlx_audio.tts", tts)
    monkeypatch.setitem(sys.modules, "mlx_audio.tts.utils", utils)
    return calls


def _line(**over):
    return {"text": "नमस्ते", "voice": "A warm voice", "speed": 1.0, "lang": "hi", **over}


def test_omnivoice_gets_its_voice_description_as_instruct(fake_mlx_audio):
    synth = tts_worker._real_loader("mlx-community/OmniVoice-bfloat16")
    synth(_line())
    assert fake_mlx_audio[0]["instruct"] == "A warm voice"
    assert "voice" not in fake_mlx_audio[0]


def test_kokoro_keeps_a_voice_argument_and_hindi_language_code(fake_mlx_audio):
    synth = tts_worker._real_loader("mlx-community/Kokoro-82M-bf16")
    synth(_line(voice="hf_alpha"))
    assert fake_mlx_audio[0]["voice"] == "hf_alpha"
    assert fake_mlx_audio[0]["lang_code"] == "h"
    assert "instruct" not in fake_mlx_audio[0]


def test_script_folder_is_taken_off_the_import_path(monkeypatch):
    monkeypatch.setattr(sys, "path", [str(HERE), "/somewhere/else"])
    tts_worker._unshadow_mlx_audio()
    assert str(HERE) not in sys.path
    assert "/somewhere/else" in sys.path


def test_a_shadowing_adapter_module_is_dropped_before_the_real_import(monkeypatch):
    shadow = types.ModuleType("mlx_audio")
    shadow.__file__ = str(HERE / "mlx_audio.py")
    monkeypatch.setitem(sys.modules, "mlx_audio", shadow)
    monkeypatch.setattr(sys, "path", [str(HERE)])
    tts_worker._unshadow_mlx_audio()
    assert "mlx_audio" not in sys.modules
