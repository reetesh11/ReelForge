import hashlib
import json
import os

import pytest
from _helpers import make_store, spec_for

from reelforge.artifacts.fingerprint import compute_inputs_fp


def test_fingerprint_stable_and_sensitive():
    base = dict(
        adapter="a", adapter_version="1", model_key="m", model_revision="r",
        prompt="p", seed=1, params={"x": 1}, input_sha256=["s"],
    )  # fmt: skip
    fp = compute_inputs_fp(**base)  # type: ignore[arg-type]
    assert fp == compute_inputs_fp(**base)  # type: ignore[arg-type]
    for k, v in (("seed", 2), ("params", {"x": 2}), ("input_sha256", ["t"])):
        assert compute_inputs_fp(**{**base, k: v}) != fp  # type: ignore[arg-type]


def test_write_lookup_take_numbers_and_active(tmp_path):
    root, _, store, pid, engine = make_store(tmp_path)
    spec = spec_for(pid)
    a = store.write(spec, b"one", ext="png")
    assert a.path.endswith("frames/s2/take_001.png") and a.take_no == 1
    assert a.sha256 == hashlib.sha256(b"one").hexdigest()
    side = json.loads(store.absolute_path(a).with_suffix(".json").read_text())
    assert side["prompt"] == a.prompt and side["model"] == "image"
    assert store.lookup(spec) is not None
    b = store.write(spec_for(pid, seed=2), b"two", ext="png")
    assert b.take_no == 2 and b.is_active
    assert store.lookup(spec) is None  # take 1 no longer active
    assert not list((root / "cache" / "tmp").iterdir())
    engine.dispose()


def test_lookup_misses_on_corruption(tmp_path):
    root, _, store, pid, engine = make_store(tmp_path)
    spec = spec_for(pid)
    a = store.write(spec, b"data", ext="png")
    path = store.absolute_path(a)
    path.write_bytes(b"data!")
    assert store.lookup(spec) is None
    path.write_bytes(b"data")
    path.with_suffix(".json").write_text("{not json")
    assert store.lookup(spec) is None
    path.with_suffix(".json").unlink()
    assert store.lookup(spec) is None
    engine.dispose()


def test_failed_rename_leaves_no_partial_files(tmp_path, monkeypatch):
    root, _, store, pid, engine = make_store(tmp_path)

    def boom(*_a, **_k):
        raise OSError("disk gone")

    monkeypatch.setattr(os, "rename", boom)
    with pytest.raises(OSError):
        store.write(spec_for(pid), b"x", ext="png")
    monkeypatch.undo()
    assert not any(p.is_file() for p in root.rglob("*") if "reelforge.db" not in p.name)
    engine.dispose()


def test_rejects_bad_inputs(tmp_path):
    root, _, store, pid, engine = make_store(tmp_path)
    with pytest.raises(ValueError):
        store.write(spec_for(pid, subdir="../x"), b"x", ext="png")
    with pytest.raises(ValueError):
        store.write(spec_for(pid), b"x", ext=".png")
    outside = tmp_path / "o.bin"
    outside.write_bytes(b"x")
    with pytest.raises(ValueError):
        store.write(spec_for(pid), outside, ext="bin")
    engine.dispose()
