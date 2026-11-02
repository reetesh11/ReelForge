"""Draw Things adapter: reachability, pinned-model check and image generation (loopback only)."""

from __future__ import annotations

import asyncio
import base64
import contextlib
import struct
from pathlib import Path
from urllib.parse import urlparse

import httpx

from reelforge.adapters._net import is_loopback_url, probe
from reelforge.adapters.base import (
    AdapterError,
    CancelToken,
    HealthReport,
    ProducedFile,
    ProgressCb,
    TaskSpec,
)

DEFAULT_PORT = 7860
DEFAULT_WIDTH = 576
DEFAULT_HEIGHT = 1024
DEFAULT_STEPS = 4
DEFAULT_STRENGTH = 0.6
MODEL_CHECK_TIMEOUT_S = 120.0
_PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"

_model_ok: set[tuple[str, str]] = set()


def port_of(url: str) -> int:
    return urlparse(url).port or DEFAULT_PORT


def unreachable_message(url: str) -> str:
    return f"Draw Things isn't reachable on port {port_of(url)}"


def _png_size(data: bytes) -> tuple[int, int] | None:
    if data[:8] == _PNG_SIGNATURE and data[12:16] == b"IHDR" and len(data) >= 24:
        width, height = struct.unpack(">II", data[16:24])
        return width, height
    return None


class DrawThingsAdapter:
    name = "draw_things"
    version = "dt-1"

    def __init__(self, url: str, *, model_id: str | None = None, timeout_s: float = 600.0) -> None:
        self.url = url
        self.model_id = model_id
        self.timeout_s = timeout_s

    def _model_check(self, model_id: str) -> HealthReport | None:
        """One tiny txt2img proving the pinned model is loaded. None means fine."""
        key = (self.url, model_id)
        if key in _model_ok:
            return None
        body = {
            "prompt": "health check",
            "seed": 0,
            "width": 128,  # Draw Things rejects anything below 128 with 422
            "height": 128,
            "steps": 1,
            "model": model_id,
        }
        try:
            resp = httpx.post(
                self.url.rstrip("/") + "/sdapi/v1/txt2img",
                json=body,
                timeout=MODEL_CHECK_TIMEOUT_S,
                trust_env=False,
            )
        except httpx.TimeoutException:
            return None  # busy rendering: counts as ok
        except httpx.HTTPError:
            return HealthReport(
                name=self.name, ok=False, detail=f"Draw Things is not reachable at {self.url}"
            )
        if resp.status_code == 422:
            return HealthReport(
                name=self.name,
                ok=False,
                detail=f"Draw Things doesn't have the model {model_id}",
                fix=f"Load {model_id} in Draw Things.",
            )
        if resp.is_success:
            _model_ok.add(key)
        return None

    def check(self) -> HealthReport:
        try:
            resp = probe(self.url)
        except ValueError as exc:
            return HealthReport(name=self.name, ok=False, detail=str(exc))
        except httpx.HTTPError:
            return HealthReport(
                name=self.name, ok=False, detail=f"Draw Things is not reachable at {self.url}"
            )
        if self.model_id:
            failed = self._model_check(self.model_id)
            if failed is not None:
                return failed
        return HealthReport(
            name=self.name,
            ok=True,
            version=self.version,
            detail=f"Draw Things reachable at {self.url} (HTTP {resp.status_code})",
        )

    async def health(self) -> HealthReport:
        return await asyncio.to_thread(self.check)

    async def capabilities(self) -> set[str]:
        return {"image"}

    async def _post(self, path: str, body: dict[str, object]) -> httpx.Response:
        async with httpx.AsyncClient(timeout=self.timeout_s, trust_env=False) as client:
            return await client.post(self.url.rstrip("/") + path, json=body)

    async def run(
        self,
        task: TaskSpec,
        out_dir: Path,
        progress: ProgressCb,
        cancel: CancelToken,
        *,
        ctx_job_id: str | None = None,
    ) -> list[ProducedFile]:
        if not is_loopback_url(self.url):
            raise AdapterError(f"{self.url} is not a loopback address; refusing to connect")
        params = task.params
        width = int(params.get("width", DEFAULT_WIDTH))
        height = int(params.get("height", DEFAULT_HEIGHT))
        steps = params["steps"] if "steps" in params else task.model.steps
        if steps is None:
            steps = DEFAULT_STEPS
        body: dict[str, object] = {
            "prompt": task.prompt,
            "seed": task.seed,
            "width": width,
            "height": height,
            "steps": int(steps),
            "model": task.model.id,
        }
        path = "/sdapi/v1/txt2img"
        if task.input_paths:
            path = "/sdapi/v1/img2img"
            body["init_images"] = [base64.b64encode(task.input_paths[0].read_bytes()).decode()]
            body["strength"] = float(params.get("strength", DEFAULT_STRENGTH))
        progress(1, "asking Draw Things")
        request = asyncio.create_task(self._post(path, body))
        waiter = asyncio.create_task(cancel.wait())
        try:
            await asyncio.wait({request, waiter}, return_when=asyncio.FIRST_COMPLETED)
            if not request.done():
                raise AdapterError("cancelled")
            resp = request.result()
        except (httpx.ConnectError, httpx.ConnectTimeout):
            raise AdapterError(unreachable_message(self.url)) from None
        except httpx.HTTPError as exc:
            raise AdapterError(f"Draw Things request failed: {type(exc).__name__}") from None
        finally:
            waiter.cancel()
            if not request.done():
                request.cancel()
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await request
        if resp.status_code == 422:
            raise AdapterError(f"Draw Things doesn't have the model {task.model.id}")
        if resp.status_code == 404 and path.endswith("img2img"):
            raise AdapterError("This Draw Things setup can't edit images")
        if not resp.is_success:
            raise AdapterError(f"Draw Things returned HTTP {resp.status_code}")
        try:
            images = resp.json()["images"]
            data = base64.b64decode(images[0])
        except (ValueError, KeyError, IndexError, TypeError):
            raise AdapterError("Draw Things returned no image") from None
        out_dir.mkdir(parents=True, exist_ok=True)
        out = out_dir / "out.png"
        out.write_bytes(data)
        size = _png_size(data) or (width, height)
        progress(99, "done")
        return [ProducedFile(path=out, ext="png", width=size[0], height=size[1])]
