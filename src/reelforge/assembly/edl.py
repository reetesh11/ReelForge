"""The edit decision list: the only input to rendering."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

FPS = 24
WIDTH = 1080
HEIGHT = 1920

CAPTION_PRESETS: dict[str, str] = {
    "bold_pop": "Bold pop",
    "clean_subtitle": "Clean subtitle",
    "hindi_devanagari": "Hindi Devanagari",
}
CAPTION_STYLES = ("auto", *CAPTION_PRESETS)


def to_frames(seconds: float) -> int:
    """Seconds to whole frames, rounding half up so durations are exact and stable."""
    return int(seconds * FPS + 0.5 + 1e-9)


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class EdlShot(_Strict):
    scene_id: str
    artifact: str
    source_duration_s: float
    in_s: float
    out_s: float
    transition_in_s: float = 0.0

    @property
    def frames(self) -> int:
        return max(0, to_frames(self.out_s - self.in_s))

    @property
    def in_frame(self) -> int:
        return to_frames(self.in_s)


class EdlDialogue(_Strict):
    scene_id: str
    artifact: str
    offset_s: float
    duration_s: float
    gain_db: float = 0.0


class EdlCaption(_Strict):
    scene_id: str
    speaker: str | None
    line_no: int
    text: str
    start_s: float
    end_s: float
    style: str | None = None


class EdlMusic(_Strict):
    tracks: list[dict[str, Any]] = Field(default_factory=list[dict[str, Any]])
    duck: bool = False


class EdlEndCard(_Strict):
    enabled: bool = False
    duration_s: float = 1.5
    template: str = "default"


class Edl(_Strict):
    version: int = 1
    fps: int = FPS
    width: int = WIDTH
    height: int = HEIGHT
    project_id: str
    video: list[EdlShot]
    dialogue: list[EdlDialogue]
    captions: list[EdlCaption]
    caption_style: str = "auto"
    music: EdlMusic = Field(default_factory=EdlMusic)
    end_card: EdlEndCard = Field(default_factory=EdlEndCard)

    def transition_frames(self, index: int) -> int:
        """Crossfade frames between shot `index - 1` and `index` (0 for a cut or the first)."""
        if index <= 0 or index >= len(self.video):
            return 0
        want = to_frames(self.video[index].transition_in_s)
        room = min(self.video[index - 1].frames, self.video[index].frames) // 2
        return max(0, min(want, room))

    def shot_start_frame(self, index: int) -> int:
        start = 0
        for i in range(index):
            start += self.video[i].frames
        for i in range(1, index + 1):
            start -= self.transition_frames(i)
        return start

    def shot_start_s(self, index: int) -> float:
        return self.shot_start_frame(index) / FPS

    @property
    def total_frames(self) -> int:
        total = sum(s.frames for s in self.video)
        return total - sum(self.transition_frames(i) for i in range(1, len(self.video)))

    @property
    def total_duration_s(self) -> float:
        return self.total_frames / FPS


def edl_hash(edl: Edl) -> str:
    canonical = json.dumps(
        edl.model_dump(mode="json"), sort_keys=True, separators=(",", ":"), ensure_ascii=False
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def load_edl(path: Path) -> Edl:
    return Edl.model_validate_json(path.read_text(encoding="utf-8"))


def save_edl(edl: Edl, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.part")
    text = json.dumps(edl.model_dump(mode="json"), indent=2, ensure_ascii=False)
    with tmp.open("w", encoding="utf-8") as fh:
        fh.write(text)
        fh.flush()
        os.fsync(fh.fileno())
    os.replace(tmp, path)
