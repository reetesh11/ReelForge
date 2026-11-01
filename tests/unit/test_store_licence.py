import json

from _helpers import make_store, spec_for


def _sidecar(store, art):
    return json.loads(store.absolute_path(art).with_suffix(".json").read_text())


def test_m1_sidecar_has_no_licence_keys(tmp_path):
    _, _, store, pid, engine = make_store(tmp_path)
    side = _sidecar(store, store.write(spec_for(pid), b"one", ext="png"))
    assert "license" not in side and "license_url" not in side
    engine.dispose()


def test_cast_sidecar_records_licence(tmp_path):
    _, _, store, pid, engine = make_store(tmp_path)
    spec = spec_for(pid, license="Non-Commercial", license_url="https://x.invalid/l")
    side = _sidecar(store, store.write(spec, b"one", ext="png"))
    assert side["license"] == "Non-Commercial"
    assert side["license_url"] == "https://x.invalid/l"
    engine.dispose()
