"""m3c: image_mem_gb setting (AC-1 .. AC-5). Public surfaces only."""

from __future__ import annotations

import re
from pathlib import Path

import pytest
from m3_helpers import RecAdapter, approved_project, cast_item, cast_url, generate
from rf_helpers import make_client, make_ctx, make_settings, run_async

ROOT = Path(__file__).resolve().parents[2]


def _toml(tmp_path: Path, body: str) -> Path:
    p = tmp_path / "config.toml"
    p.write_text(body)
    return p


def _load(tmp_path, *, cli=None, env=None, toml: str | None = None):
    from reelforge.config import load_settings

    cfg = _toml(tmp_path, toml) if toml is not None else None
    cli = {"data_root": tmp_path / "data", **(cli or {})}
    return load_settings(cli=cli, env=env or {}, config_path=cfg)


# AC-1 ---------------------------------------------------------------

def test_default_is_6():
    from reelforge.config import Settings

    assert Settings().image_mem_gb == 6.0


def test_config_toml_level(tmp_path):
    s = _load(tmp_path, toml="[limits]\nimage_mem_gb = 7.5\n")
    assert s.image_mem_gb == 7.5


def test_env_level(tmp_path):
    assert _load(tmp_path, env={"REELFORGE_IMAGE_MEM_GB": "9.5"}).image_mem_gb == 9.5


def test_cli_level(tmp_path):
    assert _load(tmp_path, cli={"image_mem_gb": 4.25}).image_mem_gb == 4.25


def test_precedence_cli_over_env_over_toml(tmp_path):
    toml = "[limits]\nimage_mem_gb = 2.0\n"
    env = {"REELFORGE_IMAGE_MEM_GB": "3.0"}
    assert _load(tmp_path, env=env, toml=toml).image_mem_gb == 3.0
    assert _load(tmp_path, env=env, toml=toml, cli={"image_mem_gb": 4.0}).image_mem_gb == 4.0


def _cli(monkeypatch, tmp_path, cmd, extra):
    from reelforge import cli as cli_mod
    from typer.testing import CliRunner

    seen: list = []
    if cmd == "doctor":
        monkeypatch.setattr(cli_mod, "run_doctor", lambda s: seen.append(s) or None)
        monkeypatch.setattr(cli_mod, "format_report", lambda r: [])
    else:
        monkeypatch.setattr(cli_mod, "run_up", lambda s, allow_degraded=False: seen.append(s) or 0)
    res = CliRunner().invoke(
        cli_mod.app, [cmd, "--data-root", str(tmp_path / "data"), *extra]
    )
    return res, seen


@pytest.mark.parametrize("cmd", ["up", "doctor"])
def test_cli_flag_reaches_settings(monkeypatch, tmp_path, cmd):
    res, seen = _cli(monkeypatch, tmp_path, cmd, ["--image-mem-gb", "3.5"])
    assert seen, res.output
    assert seen[0].image_mem_gb == 3.5


@pytest.mark.parametrize("cmd", ["up", "doctor"])
def test_cli_help_lists_flag(cmd):
    from reelforge.cli import app
    from typer.testing import CliRunner

    out = CliRunner().invoke(app, [cmd, "--help"]).output
    assert "--image-mem-gb" in out


# AC-2 ---------------------------------------------------------------

BAD = ["0", "-1", "abc"]


@pytest.mark.parametrize("bad", ["0", "-1", "abc", ""])
def test_env_rejects_bad(tmp_path, bad):
    from reelforge.config import ConfigError

    with pytest.raises(ConfigError) as ei:
        _load(tmp_path, env={"REELFORGE_IMAGE_MEM_GB": bad})
    assert ei.value.key == "image_mem_gb" and "image_mem_gb" in str(ei.value)


@pytest.mark.parametrize("bad", ["0", "-1", '"abc"'])
def test_toml_rejects_bad(tmp_path, bad):
    from reelforge.config import ConfigError

    with pytest.raises(ConfigError) as ei:
        _load(tmp_path, toml=f"[limits]\nimage_mem_gb = {bad}\n")
    assert ei.value.key == "image_mem_gb" and "image_mem_gb" in str(ei.value)


@pytest.mark.parametrize("bad", [0, -1, "abc"])
def test_cli_mapping_rejects_bad(tmp_path, bad):
    from reelforge.config import ConfigError

    assert _load(tmp_path, cli={"image_mem_gb": 2.0}).image_mem_gb == 2.0

    with pytest.raises(ConfigError) as ei:
        _load(tmp_path, cli={"image_mem_gb": bad})
    assert ei.value.key == "image_mem_gb" and "image_mem_gb" in str(ei.value)


@pytest.mark.parametrize("bad", [0, -1, "abc"])
def test_settings_direct_rejects_bad(bad):
    from pydantic import ValidationError
    from reelforge.config import Settings

    assert Settings(image_mem_gb=1.0).image_mem_gb == 1.0
    with pytest.raises(ValidationError):
        Settings(image_mem_gb=bad)


def test_small_positive_accepted(tmp_path):
    assert _load(tmp_path, cli={"image_mem_gb": 0.5}).image_mem_gb == 0.5


@pytest.mark.parametrize("cmd", ["up", "doctor"])
@pytest.mark.parametrize("bad", ["0", "-1", "abc"])
def test_cli_bad_value_exits_2(monkeypatch, tmp_path, cmd, bad):
    ok, ok_seen = _cli(monkeypatch, tmp_path, cmd, ["--image-mem-gb=1.5"])
    assert ok_seen and ok_seen[0].image_mem_gb == 1.5  # flag exists and works
    res, seen = _cli(monkeypatch, tmp_path, cmd, [f"--image-mem-gb={bad}"])
    assert res.exit_code == 2 and not seen
    out = res.output.replace("-", "_")  # typer may reject non-numbers itself, naming --image-mem-gb
    assert "image_mem_gb" in out


# AC-3 ---------------------------------------------------------------

def _world(tmp_path, available_gb=64.0, **over):
    settings = make_settings(tmp_path, **over)
    ctx = make_ctx(settings, adapter=RecAdapter(settings), available_gb=available_gb)
    return ctx, make_client(ctx)


def _all_three(client, ctx, pid):
    r1, _ = generate(client, ctx, pid, "tomato", seed=1)
    r2, _ = generate(client, ctx, pid, "tomato", regenerate=True)
    cand = cast_item(client, pid, "tomato")["candidates"][0]["id"]
    r3, _ = generate(
        client, ctx, pid, "tomato",
        refine={"from_candidate": cand, "instruction": "wear a blue hat"},
    )
    return r1, r2, r3


def test_mem_need_default(tmp_path):
    ctx, client = _world(tmp_path)
    with client:
        pid = approved_project(client)
        for r in _all_three(client, ctx, pid):
            assert r["mem_need_gb"] == 6.0


def test_mem_need_configured(tmp_path):
    ctx, client = _world(tmp_path, image_mem_gb=3.5)
    with client:
        pid = approved_project(client)
        for r in _all_three(client, ctx, pid):
            assert r["mem_need_gb"] == 3.5


# AC-4 ---------------------------------------------------------------

def test_cast_preflight_failure_message(tmp_path):
    ctx, client = _world(tmp_path, available_gb=2.0, image_mem_gb=3.5)
    with client:
        pid = approved_project(client)
        _, job = generate(client, ctx, pid, "tomato", seed=1)
        want = "Only 2.0 GB free, job needs 3.5 GB. Close other apps, or lower image_mem_gb in config.toml."
        assert job.status == "failed"
        assert job.error == want and job.message == want


def test_cast_succeeds_when_memory_enough(tmp_path):
    ctx, client = _world(tmp_path, available_gb=4.0, image_mem_gb=3.5)
    with client:
        pid = approved_project(client)
        _, job = generate(client, ctx, pid, "tomato", seed=1)
        assert job.status == "succeeded", job.error


# AC-5 / docs --------------------------------------------------------

def test_no_generate_mem_gb_in_src():
    for p in (ROOT / "src").rglob("*.py"):
        assert "GENERATE_MEM_GB" not in p.read_text(), p
    import reelforge.api.routes_cast as rc

    assert not hasattr(rc, "GENERATE_MEM_GB")
    assert not re.search(r"mem_need_gb\s*=\s*\d", (ROOT / "src/reelforge/api/routes_cast.py").read_text())


def test_manual_checks_m3_documents_setting():
    text = (ROOT / "docs" / "manual-checks.md").read_text()
    start = text.index("M3 Cast (AC-13)")
    m = re.search(r"^#+ ", text[start + 1 :], re.M)
    section = text[start : start + 1 + m.start()] if m else text[start:]
    for needle in ["image_mem_gb", "REELFORGE_IMAGE_MEM_GB", "--image-mem-gb", "[limits]",
                   "Only X GB free, job needs Y GB"]:
        assert needle in section, needle
