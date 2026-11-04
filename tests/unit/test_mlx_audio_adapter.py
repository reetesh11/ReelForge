import asyncio
import json
import re
import subprocess
import wave

import pytest

from reelforge.adapters import mlx_audio
from reelforge.adapters.base import AdapterError, CancelToken
from reelforge.adapters.mlx_audio import (
    MlxAudioAdapter,
    VoiceLine,
    check_pause,
    check_speed,
    plan_speed,
    postprocess_wav,
)


def _vl(i, text, speed=1.0):
    return VoiceLine(id=f"v{i}", text=text, voice="x", ref_audio=None, ref_text=None, speed=speed)


def _lufs(path):
    r = subprocess.run(
        ["ffmpeg", "-nostats", "-i", str(path), "-af", "ebur128", "-f", "null", "-"],
        capture_output=True,
        text=True,
        timeout=60,
    )
    return float(re.findall(r"I:\s+(-?\d+\.\d+) LUFS", r.stderr)[-1])


def _tone(tmp_path, text, speed=1.0):
    from reelforge.adapters.tts_worker import run_batch

    line = {
        "id": "t",
        "text": text,
        "model": "m",
        "voice": None,
        "ref_audio": None,
        "ref_text": None,
        "speed": speed,
        "lang": "hi",
    }
    run_batch([line], tmp_path / "raw", backend="mock", emit=lambda e: None)
    return tmp_path / "raw" / "t.wav"


def test_bounds():
    assert check_speed(0.8) == 0.8 and check_speed(1.25) == 1.25
    with pytest.raises(ValueError):
        check_speed(float("nan"))
    with pytest.raises(ValueError, match="pause_before must be between 0 and 1 seconds"):
        check_pause("pause_before", 1.5)


def test_plan_speed():
    assert plan_speed("kokoro", 1.2) == (1.2, None)
    assert plan_speed("omnivoice", 0.9) == (1.0, 0.9)


def test_postprocess_trims_normalises_and_scales(tmp_path):
    src = _tone(tmp_path, "ek do teen char paanch")
    a, b = tmp_path / "a.wav", tmp_path / "b.wav"
    d1 = asyncio.run(postprocess_wav(src, a))
    d2 = asyncio.run(postprocess_wav(src, b, atempo=0.8))
    with wave.open(str(a)) as w:
        assert (w.getframerate(), w.getnchannels(), w.getsampwidth()) == (48000, 1, 2)
    assert abs(_lufs(a) - -16.0) <= 1.0
    assert d2 == pytest.approx(d1 / 0.8, rel=0.05)
    assert d1 < (0.3 + 0.25 * 5) + 0.2  # the 0.6 s of edge silence is gone


def test_postprocess_cancelled(tmp_path):
    src = _tone(tmp_path, "ek do")
    cancel = CancelToken()
    cancel.cancel()
    with pytest.raises(AdapterError):
        asyncio.run(postprocess_wav(src, tmp_path / "x.wav", cancel=cancel))


def test_run_batch_mock_delivers_each_line_once(tmp_path):
    got, prog = [], []
    res = asyncio.run(
        MlxAudioAdapter(None, backend="mock").run_batch(
            [_vl(0, "ek do"), _vl(1, "[[fail]]"), _vl(2, "teen char paanch")],
            "org/model",
            "kokoro",
            tmp_path / "o",
            lambda p, m: prog.append(m),
            CancelToken(),
            on_line=got.append,
        )
    )
    assert [r.id for r in got] == ["v0", "v1", "v2"] and [r.id for r in res] == ["v0", "v1", "v2"]
    assert res[1].error and res[0].duration_s and res[2].duration_s
    assert prog[-1] == "line 3 of 3"
    batch = [json.loads(x) for x in (tmp_path / "o" / "batch.jsonl").read_text().splitlines()]
    assert {r["model"] for r in batch} == {"org/model"}


def test_crash_keeps_delivered_lines_and_maps_error(tmp_path, monkeypatch):
    script = tmp_path / "w.py"
    script.write_text(
        "import json, sys\n"
        "print(json.dumps({'id': 'v0', 'error': 'x'}), flush=True)\n"
        "sys.stderr.write('kaboom\\n')\n"
        "sys.exit(4)\n"
    )
    monkeypatch.setattr(mlx_audio, "WORKER_PATH", script)
    got = []
    with pytest.raises(AdapterError, match="^Voice engine stopped: kaboom$"):
        asyncio.run(
            MlxAudioAdapter(None, backend="mock").run_batch(
                [_vl(0, "a"), _vl(1, "b")],
                "m",
                "omnivoice",
                tmp_path / "o",
                lambda p, m: None,
                CancelToken(),
                on_line=got.append,
            )
        )
    assert [r.id for r in got] == ["v0"]


def test_timeout_maps_to_voice_engine_stopped(tmp_path, monkeypatch):
    script = tmp_path / "w.py"
    script.write_text("import time\ntime.sleep(30)\n")
    monkeypatch.setattr(mlx_audio, "WORKER_PATH", script)
    with pytest.raises(AdapterError, match="^Voice engine stopped: timed out after 1s$"):
        asyncio.run(
            MlxAudioAdapter(None, backend="mock", timeout_s=1).run_batch(
                [_vl(0, "a")], "m", "omnivoice", tmp_path / "o", lambda p, m: None, CancelToken()
            )
        )


def test_selftest_without_environment():
    rep = MlxAudioAdapter(None).selftest()
    assert not rep.ok and rep.detail.startswith("tts_worker selftest failed: ")


def test_selftest_mock_backend_passes():
    assert MlxAudioAdapter(None, backend="mock").selftest().ok
