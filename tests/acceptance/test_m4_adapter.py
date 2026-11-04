"""m4 AC-5 (post-processing), AC-4 (one subprocess per batch), AC-6 (doctor), AC-7 (batch model id)."""

from __future__ import annotations

import asyncio
import json
import re
import stat
import subprocess
import sys

import pytest
from m4_helpers import read_wav, wav_bytes, wav_seconds, wrap_worker
from rf_helpers import run_async

from reelforge.adapters.base import AdapterError, CancelToken


def _mock_wav(tmp_path, text: str, speed: float = 1.0):
    from reelforge.adapters.tts_worker import run_batch

    out = tmp_path / "raw"
    line = {"id": "r", "text": text, "model": "m", "voice": None, "ref_audio": None,
            "ref_text": None, "speed": speed, "lang": "hi"}
    ev: list[dict] = []
    assert run_batch([line], out, backend="mock", emit=ev.append) == 0
    return out / "r.wav"


def _lufs(path) -> float:
    r = subprocess.run(["ffmpeg", "-nostats", "-i", str(path), "-af", "ebur128", "-f", "null", "-"],
                       capture_output=True, text=True, timeout=60)
    m = re.findall(r"I:\s+(-?\d+\.\d+) LUFS", r.stderr)
    return float(m[-1])


def test_postprocess_48k_minus16_lufs_trimmed(tmp_path):
    from reelforge.adapters.mlx_audio import postprocess_wav

    src = _mock_wav(tmp_path, "ek do teen char")
    dst = tmp_path / "pp.wav"
    dur = run_async(postprocess_wav(src, dst))
    samples, rate, ch, width = read_wav(dst)
    assert (rate, ch, width) == (48000, 1, 2)
    assert dur == pytest.approx(len(samples) / rate, abs=0.05)
    assert abs(_lufs(dst) - (-16.0)) <= 1.0
    assert dur < wav_seconds(src) - 0.3  # leading and trailing silence removed
    head, tail = samples[: int(0.05 * rate)], samples[-int(0.05 * rate):]
    assert max(abs(x) for x in head) > 500 and max(abs(x) for x in tail) > 500


def test_postprocess_normalises_quiet_and_loud_input(tmp_path):
    from reelforge.adapters.mlx_audio import postprocess_wav

    for name, amp in (("quiet", 0.02), ("loud", 0.95)):
        src = tmp_path / f"{name}.wav"
        src.write_bytes(wav_bytes(1.5, amp=amp))
        dst = tmp_path / f"{name}.pp.wav"
        run_async(postprocess_wav(src, dst))
        assert abs(_lufs(dst) - (-16.0)) <= 1.0, name


def test_postprocess_atempo_shortens(tmp_path):
    from reelforge.adapters.mlx_audio import postprocess_wav

    src = _mock_wav(tmp_path, "ek do teen char paanch chhe")
    a, b = tmp_path / "a.wav", tmp_path / "b.wav"
    d1 = run_async(postprocess_wav(src, a))
    d2 = run_async(postprocess_wav(src, b, atempo=1.25))
    assert d2 == pytest.approx(d1 / 1.25, abs=0.08)


def test_postprocess_bad_input_raises_adapter_error(tmp_path):
    from reelforge.adapters.mlx_audio import postprocess_wav

    bad = tmp_path / "bad.wav"
    bad.write_bytes(b"not audio at all")
    with pytest.raises(AdapterError):
        run_async(postprocess_wav(bad, tmp_path / "out.wav"))


def _vlines(texts):
    from reelforge.adapters.mlx_audio import VoiceLine

    return [VoiceLine(id=f"v{i}", text=t, voice="x", ref_audio=None, ref_text=None, speed=1.0)
            for i, t in enumerate(texts)]


def test_run_batch_one_subprocess_postprocessed_results_and_progress(tmp_path, monkeypatch):
    from reelforge.adapters.mlx_audio import MlxAudioAdapter

    log = wrap_worker(tmp_path, monkeypatch)
    adapter = MlxAudioAdapter(None, backend="mock")
    got, prog = [], []
    out = tmp_path / "out"
    res = run_async(adapter.run_batch(
        _vlines(["ek do teen", "yeh [[fail]] hai", "char paanch chhe"]), "org/Model-Z", "omnivoice", out,
        lambda p, m: prog.append((p, m)), CancelToken(), on_line=got.append))
    calls = [json.loads(x) for x in log.read_text().splitlines()]
    assert len(calls) == 1  # one subprocess for the whole batch
    assert "--backend" in calls[0]["argv"] and "mock" in calls[0]["argv"]
    rows = [json.loads(x) for x in calls[0]["batch"].splitlines() if x.strip()]
    assert [r["id"] for r in rows] == ["v0", "v1", "v2"]
    assert all(r["model"] == "org/Model-Z" and r["lang"] == "hi" for r in rows)
    assert [r.id for r in res] == ["v0", "v1", "v2"] and len(got) == 3
    assert res[1].error and res[1].path is None
    for r in (res[0], res[2]):
        assert r.error is None and r.path == out / f"{r.id}.48k.wav" and r.path.exists()
        assert read_wav(r.path)[1] == 48000 and r.duration_s > 0
    assert prog, "progress must be reported"


def test_run_batch_omnivoice_sends_worker_speed_1_kokoro_native(tmp_path, monkeypatch):
    from reelforge.adapters.mlx_audio import MlxAudioAdapter, VoiceLine

    log = wrap_worker(tmp_path, monkeypatch)
    adapter = MlxAudioAdapter(None, backend="mock")
    for vm in ("omnivoice", "kokoro"):
        ln = VoiceLine(id=vm, text="ek do teen char", voice="x", ref_audio=None, ref_text=None, speed=1.25)
        run_async(adapter.run_batch([ln], "id/x", vm, tmp_path / vm, lambda p, m: None, CancelToken()))
    rows = {}
    for x in log.read_text().splitlines():
        r = json.loads(json.loads(x)["batch"].splitlines()[0])
        rows[r["id"]] = r
    assert rows["omnivoice"]["speed"] == 1.0
    assert rows["kokoro"]["speed"] == 1.25


def test_run_batch_rejects_out_of_range_speed(tmp_path, monkeypatch):
    from reelforge.adapters.mlx_audio import MlxAudioAdapter, VoiceLine

    wrap_worker(tmp_path, monkeypatch)
    ln = VoiceLine(id="a", text="ek", voice="x", ref_audio=None, ref_text=None, speed=1.5)
    with pytest.raises(ValueError):
        run_async(MlxAudioAdapter(None, backend="mock").run_batch(
            [ln], "id/x", "kokoro", tmp_path / "o", lambda p, m: None, CancelToken()))


def test_run_batch_crash_raises_voice_engine_stopped(tmp_path, monkeypatch):
    from reelforge.adapters.mlx_audio import MlxAudioAdapter

    wrap_worker(tmp_path, monkeypatch, body="sys.stderr.write('model exploded\\n')\nsys.exit(3)\n")
    with pytest.raises(AdapterError, match=r"^Voice engine stopped: "):
        run_async(MlxAudioAdapter(None, backend="mock").run_batch(
            _vlines(["ek do"]), "id/x", "omnivoice", tmp_path / "o", lambda p, m: None, CancelToken()))


def test_run_batch_cancel(tmp_path, monkeypatch):
    from reelforge.adapters.mlx_audio import MlxAudioAdapter

    wrap_worker(tmp_path, monkeypatch, body="import time\ntime.sleep(60)\n")
    cancel = CancelToken()

    async def go():
        task = asyncio.ensure_future(MlxAudioAdapter(None, backend="mock", timeout_s=120).run_batch(
            _vlines(["ek do"]), "id/x", "omnivoice", tmp_path / "o", lambda p, m: None, cancel))
        await asyncio.sleep(1.0)
        cancel.cancel()
        return await asyncio.wait_for(task, 20)

    with pytest.raises(AdapterError, match="cancelled"):
        run_async(go())


def test_presets_per_model():
    from reelforge.adapters.mlx_audio import PRESETS, VOICE_MODELS

    assert VOICE_MODELS == {"omnivoice": "tts", "kokoro": "tts_fallback"}
    assert [p.id for p in PRESETS["kokoro"]] == ["hf_alpha", "hf_beta", "hm_omega", "hm_psi"]
    assert all(p.voice == p.id for p in PRESETS["kokoro"])
    assert [p.id for p in PRESETS["omnivoice"]] == ["asha", "ravi"]
    assert all(p.voice and p.voice != p.id for p in PRESETS["omnivoice"])


# doctor (AC-6) -----------------------------------------------------------

def _fake_env(tmp_path, exit_code: int, stderr: str = ""):
    proj = tmp_path / "mlx-audio"
    py = proj / ".venv" / "bin" / "python"
    py.parent.mkdir(parents=True)
    py.write_text(f"#!/bin/sh\necho {stderr!r} >&2\nexit {exit_code}\n")
    py.chmod(py.stat().st_mode | stat.S_IXUSR)
    return proj


def test_doctor_passes_when_selftest_passes(tmp_path):
    from reelforge.config import Settings
    from reelforge.doctor import check_mlx_audio

    r = check_mlx_audio(Settings(data_root=tmp_path / "d", mlx_audio_path=_fake_env(tmp_path, 0)))
    assert r.name == "mlx_audio" and r.status == "pass" and r.severity == "blocking"
    assert r.detail == "mlx-audio ready (selftest passed)"


def test_doctor_blocking_failure_when_selftest_fails(tmp_path):
    from reelforge.config import Settings
    from reelforge.doctor import check_mlx_audio

    r = check_mlx_audio(Settings(data_root=tmp_path / "d",
                                 mlx_audio_path=_fake_env(tmp_path, 1, "model load failed")))
    assert r.status == "fail" and r.severity == "blocking"
    assert r.detail.startswith("tts_worker selftest failed: ") and "model load failed" in r.detail
    assert r.fix and "cpython-3.12-macos-aarch64-none" in r.fix


def test_doctor_blocking_failure_when_env_missing(tmp_path):
    from reelforge.config import Settings
    from reelforge.doctor import check_mlx_audio

    missing = tmp_path / "nope"
    r = check_mlx_audio(Settings(data_root=tmp_path / "d", mlx_audio_path=missing))
    assert r.status == "fail" and r.severity == "blocking"
    assert r.detail == f"mlx-audio project not found at {missing}"
    assert r.fix and "cpython-3.12-macos-aarch64-none" in r.fix


def test_adapter_selftest_report(tmp_path):
    from reelforge.adapters.mlx_audio import MlxAudioAdapter

    ok = MlxAudioAdapter(_fake_env(tmp_path, 0)).selftest()
    assert ok.ok is True
    bad = MlxAudioAdapter(_fake_env(tmp_path / "x", 2, "kaput")).selftest()
    assert bad.ok is False and bad.detail == "tts_worker selftest failed: kaput"
    assert sys.version  # keep import used
