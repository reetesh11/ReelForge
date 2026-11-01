from pathlib import Path

from reelforge.api.openapi_export import export

ROOT = Path(__file__).resolve().parents[2]


def test_committed_schema_matches_export(tmp_path):
    out = tmp_path / "openapi.json"
    export(out)
    assert (ROOT / "web" / "openapi.json").read_text() == out.read_text(), (
        "run: uv run python -m reelforge.api.openapi_export web/openapi.json"
    )
