"""Export the OpenAPI schema (used to generate the typed web client).

Regenerate the committed file with:
    uv run python -m reelforge.api.openapi_export web/openapi.json
"""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

from reelforge.api.app import create_app
from reelforge.config import Settings
from reelforge.context import AppContext
from reelforge.doctor import DoctorReport


def export(path: Path) -> None:
    with tempfile.TemporaryDirectory(prefix="reelforge-openapi-") as tmp:
        ctx = AppContext.create(
            Settings(data_root=Path(tmp) / "data"),
            doctor=lambda: DoctorReport(checks=[]),
        )
        try:
            schema = create_app(ctx, start_worker=False).openapi()
        finally:
            ctx.close()
    path.write_text(json.dumps(schema, indent=2, sort_keys=True) + "\n", encoding="utf-8")


if __name__ == "__main__":
    export(Path(sys.argv[1] if len(sys.argv) > 1 else "web/openapi.json"))
