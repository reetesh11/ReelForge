"""Range-capable media route confined to the data root."""

from __future__ import annotations

import mimetypes
import re
from collections.abc import Iterator
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import Response, StreamingResponse

from reelforge.context import AppContext
from reelforge.db.models import Artifact

CHUNK = 1 << 20
MIME_OVERRIDES = {".wav": "audio/wav", ".mp4": "video/mp4", ".png": "image/png"}
_RANGE_RE = re.compile(r"^bytes=(\d*)-(\d*)$")


def parse_range(header: str, size: int) -> tuple[int, int] | str | None:
    """Return (start, end) inclusive, 'unsatisfiable', or None when the header is ignored."""
    match = _RANGE_RE.match(header.strip())
    if match is None:
        return None
    first, last = match.group(1), match.group(2)
    if first == "" and last == "":
        return None
    if first == "":
        suffix = int(last)
        if suffix == 0 or size == 0:
            return "unsatisfiable"
        return max(size - suffix, 0), size - 1
    start = int(first)
    if start >= size:
        return "unsatisfiable"
    end = size - 1 if last == "" else min(int(last), size - 1)
    if end < start:
        return None
    return start, end


def _iter_file(path: Path, start: int, end: int) -> Iterator[bytes]:
    remaining = end - start + 1
    with path.open("rb") as fh:
        fh.seek(start)
        while remaining > 0:
            chunk = fh.read(min(CHUNK, remaining))
            if not chunk:
                break
            remaining -= len(chunk)
            yield chunk


def build_router(ctx: AppContext) -> APIRouter:
    router = APIRouter(tags=["media"])

    @router.get("/media/{artifact_id}")
    async def get_media(artifact_id: str, request: Request) -> Response:
        with ctx.session_factory() as s:
            artifact = s.get(Artifact, artifact_id)
        if artifact is None:
            raise HTTPException(404, "artifact not found")
        root = ctx.settings.data_root.resolve()
        path = (root / artifact.path).resolve()
        if not path.is_relative_to(root):
            raise HTTPException(403, "path outside data root")
        if not path.is_file():
            raise HTTPException(404, "file missing")
        size = path.stat().st_size
        ctype = MIME_OVERRIDES.get(path.suffix.lower()) or (
            mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        )
        headers = {"Accept-Ranges": "bytes"}
        header = request.headers.get("range")
        parsed = parse_range(header, size) if header else None
        if parsed == "unsatisfiable":
            return Response(
                status_code=416, headers={**headers, "Content-Range": f"bytes */{size}"}
            )
        if isinstance(parsed, tuple):
            start, end = parsed
            return StreamingResponse(
                _iter_file(path, start, end),
                status_code=206,
                media_type=ctype,
                headers={
                    **headers,
                    "Content-Range": f"bytes {start}-{end}/{size}",
                    "Content-Length": str(end - start + 1),
                },
            )
        return StreamingResponse(
            _iter_file(path, 0, size - 1),
            media_type=ctype,
            headers={**headers, "Content-Length": str(size)},
        )

    return router
