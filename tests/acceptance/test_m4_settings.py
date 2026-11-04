"""m4 AC-7 (models.toml, voice_model, status) and the settings part of AC-10 (voice_mem_gb)."""

from __future__ import annotations

from pathlib import Path

import pytest
from m4_helpers import voice_world
from rf_helpers import make_client, make_ctx, make_settings

ROOT = Path(__file__).resolve().parents[2]


def _load(tmp_path, *, cli=None, env=None, toml: str | None = None):
    from reelforge.config import load_settings

    cfg = None
    if toml is not None:
        cfg = tmp_path / "config.toml"
        cfg.write_text(toml)
    return load_settings(cli={"data_root": tmp_path / "data", **(cli or {})}, env=env or {}, config_path=cfg)


# models.toml ---------------------------------------------------------------

def test_packaged_models_toml_omnivoice_and_kokoro():
    from reelforge.models_registry import load_models

    reg = load_models(ROOT / "src" / "reelforge" / "models.toml")
    tts = reg.get("tts")
    assert tts.id == "mlx-community/OmniVoice-bfloat16" and tts.license == "Apache-2.0"
    assert tts.license_url.startswith("http")
    fb = reg.get("tts_fallback")
    assert fb.id == "mlx-community/Kokoro-82M-bf16" and fb.license == "Apache-2.0"
    assert fb.license_url.startswith("http")
    assert reg.missing_license() == []


def test_licence_doctor_check_has_no_warning_for_packaged_models(tmp_path):
    from reelforge.config import Settings
    from reelforge.doctor import check_licenses

    from reelforge.models_registry import load_models

    s = Settings(data_root=tmp_path / "d")
    assert {"tts", "tts_fallback"} <= set(load_models(s.models_path).keys())
    assert check_licenses(s).status == "pass"


# voice_model ---------------------------------------------------------------

def test_voice_model_default_and_levels(tmp_path):
    from reelforge.config import Settings

    assert Settings().voice_model == "omnivoice"
    assert _load(tmp_path, toml='[runtime]\nvoice_model = "kokoro"\n').voice_model == "kokoro"
    assert _load(tmp_path, env={"REELFORGE_VOICE_MODEL": "kokoro"}).voice_model == "kokoro"
    assert _load(tmp_path, cli={"voice_model": "kokoro"}).voice_model == "kokoro"
    toml = '[runtime]\nvoice_model = "kokoro"\n'
    assert _load(tmp_path, toml=toml, env={"REELFORGE_VOICE_MODEL": "omnivoice"}).voice_model == "omnivoice"


def test_voice_model_unknown_names_choices(tmp_path):
    from reelforge.config import ConfigError

    with pytest.raises(ConfigError) as ei:
        _load(tmp_path, env={"REELFORGE_VOICE_MODEL": "bark"})
    assert "omnivoice" in str(ei.value) and "kokoro" in str(ei.value)


@pytest.mark.parametrize("cmd", ["up", "doctor"])
def test_voice_flags_reach_settings_and_help(monkeypatch, tmp_path, cmd):
    from reelforge import cli as cli_mod
    from typer.testing import CliRunner

    seen: list = []
    if cmd == "doctor":
        monkeypatch.setattr(cli_mod, "run_doctor", lambda s: seen.append(s) or None)
        monkeypatch.setattr(cli_mod, "format_report", lambda r: [])
    else:
        monkeypatch.setattr(cli_mod, "run_up", lambda s, allow_degraded=False: seen.append(s) or 0)
    res = CliRunner().invoke(cli_mod.app, [cmd, "--data-root", str(tmp_path / "d"),
                                           "--voice-model", "kokoro", "--voice-mem-gb", "2.5"])
    assert seen, res.output
    assert seen[0].voice_model == "kokoro" and seen[0].voice_mem_gb == 2.5
    out = CliRunner().invoke(cli_mod.app, [cmd, "--help"]).output
    assert "--voice-model" in out and "--voice-mem-gb" in out


# voice_mem_gb --------------------------------------------------------------

def test_voice_mem_default_and_precedence(tmp_path):
    from reelforge.config import Settings

    assert Settings().voice_mem_gb == 4.0
    toml = "[limits]\nvoice_mem_gb = 2.0\n"
    env = {"REELFORGE_VOICE_MEM_GB": "3.0"}
    assert _load(tmp_path, toml=toml).voice_mem_gb == 2.0
    assert _load(tmp_path, toml=toml, env=env).voice_mem_gb == 3.0
    assert _load(tmp_path, toml=toml, env=env, cli={"voice_mem_gb": 5.5}).voice_mem_gb == 5.5
    assert _load(tmp_path, cli={"voice_mem_gb": 0.5}).voice_mem_gb == 0.5


@pytest.mark.parametrize("bad", ["0", "-1", "abc", "nan", "inf"])
def test_voice_mem_rejects_bad_everywhere(tmp_path, bad):
    from reelforge.config import ConfigError

    with pytest.raises(ConfigError) as ei:
        _load(tmp_path, env={"REELFORGE_VOICE_MEM_GB": bad})
    assert ei.value.key == "voice_mem_gb"
    if bad not in ("abc", "nan", "inf"):
        with pytest.raises(ConfigError) as ei:
            _load(tmp_path, toml=f"[limits]\nvoice_mem_gb = {bad}\n")
        assert ei.value.key == "voice_mem_gb"
        with pytest.raises(ConfigError) as ei:
            _load(tmp_path, cli={"voice_mem_gb": float(bad)})
        assert ei.value.key == "voice_mem_gb"


# HTTP / status ---------------------------------------------------------------

def test_voice_model_endpoint_get_put(tmp_path):
    ctx, client = voice_world(tmp_path)
    with client:
        r = client.get("/api/v1/voice-model")
        assert r.status_code == 200
        assert r.json() == {
            "voice_model": "omnivoice", "label": "OmniVoice",
            "model_id": "mlx-community/OmniVoice-bfloat16",
            "choices": [{"key": "omnivoice", "label": "OmniVoice"},
                        {"key": "kokoro", "label": "Kokoro (fallback)"}],
        }
        r = client.put("/api/v1/voice-model", json={"voice_model": "kokoro"})
        assert r.status_code == 200
        assert r.json()["voice_model"] == "kokoro" and r.json()["label"] == "Kokoro (fallback)"
        assert r.json()["model_id"] == "mlx-community/Kokoro-82M-bf16"
        assert client.get("/api/v1/voice-model").json()["voice_model"] == "kokoro"
        bad = client.put("/api/v1/voice-model", json={"voice_model": "bark"})
        assert bad.status_code == 422 and "omnivoice" in bad.text and "kokoro" in bad.text
        assert client.get("/api/v1/voice-model").json()["voice_model"] == "kokoro"


def test_current_voice_model_runtime_choice_over_settings(tmp_path):
    from reelforge.voice.service import current_voice_model

    settings = make_settings(tmp_path, voice_model="kokoro")
    ctx = make_ctx(settings)
    with make_client(ctx) as client:
        assert current_voice_model(ctx) == "kokoro"
        client.put("/api/v1/voice-model", json={"voice_model": "omnivoice"})
        assert current_voice_model(ctx) == "omnivoice"


def test_batch_model_id_follows_voice_model(tmp_path, monkeypatch):
    """The adapter writes the selected model id into the batch (AC-7)."""
    import json

    from m4_helpers import cast_approved, generate
    from m4_helpers import wrap_worker

    ctx, client = voice_world(tmp_path)
    with client:
        log = wrap_worker(tmp_path, monkeypatch)
        pid = cast_approved(client, ctx)
        client.put("/api/v1/voice-model", json={"voice_model": "kokoro"})
        voices = client.get(f"/api/v1/projects/{pid}/voices").json()
        assert [p["id"] for p in voices["presets"]] == ["hf_alpha", "hf_beta", "hm_omega", "hm_psi"]
        assert voices["voice_model"]["key"] == "kokoro"
        for key, vid in (("tomato", "hm_omega"), ("potato", "hf_alpha")):
            r = client.post(f"/api/v1/projects/{pid}/voices/characters/{key}:set",
                            json={"mode": "preset", "voice_id": vid})
            assert r.status_code == 200, r.text
        _, job = generate(client, ctx, pid)
        assert job.status == "succeeded", job.error
        rows = [json.loads(ln) for c in log.read_text().splitlines()
                for ln in json.loads(c)["batch"].splitlines() if ln.strip()]
        assert rows and {r["model"] for r in rows} == {"mlx-community/Kokoro-82M-bf16"}


# docs ------------------------------------------------------------------------

def test_manual_checks_records_voice_section():
    text = (ROOT / "docs" / "manual-checks.md").read_text()
    for needle in ["voice_mem_gb", "OmniVoice", "Kokoro"]:
        assert needle in text, needle
