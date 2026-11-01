"""Request and response models for the HTTP API."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

StageName = Literal[
    "DRAFT",
    "STORY_APPROVED",
    "CAST_APPROVED",
    "VOICES_APPROVED",
    "FRAMES_APPROVED",
    "SHOTS_APPROVED",
    "ASSEMBLED",
    "EXPORTED",
]
JobStatus = Literal["queued", "running", "succeeded", "failed", "cancelled"]
StageState = Literal[
    "not_started", "queued", "rendering", "needs_review", "approved", "stale", "failed"
]


class ProjectCreate(BaseModel):
    title: str = Field(min_length=1, max_length=200)


class ProjectPatch(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=200)
    stage: StageName | None = None


class ProjectOut(BaseModel):
    id: str
    slug: str
    title: str
    data_dir: str
    stage: StageName
    stages_approved: int = Field(ge=0, le=6)
    brand_kit_id: str | None
    created_at: datetime
    updated_at: datetime


class StageInfo(BaseModel):
    key: str
    label: str
    state: StageState
    progress: int | None
    locked: bool


class StagesOut(BaseModel):
    stages: list[StageInfo]


class ArtifactBody(BaseModel):
    owner_type: str
    owner_id: str
    kind: str
    media: Literal["image", "audio", "video"]
    prompt: str
    seed: int
    model_key: str | None = None
    params: dict[str, Any] = {}
    input_artifact_ids: list[str] = []
    subdir: str | None = None
    stage: Literal["story", "cast", "voices", "frames", "shots", "assembly"] | None = None
    heavy: bool = False
    mem_need_gb: float = 0.0


class ArtifactResult(BaseModel):
    cache_hit: bool
    artifact_id: str | None
    job_id: str | None


class JobOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    project_id: str | None
    type: str
    status: JobStatus
    priority: int
    heavy: bool
    mem_need_gb: float
    attempts: int
    progress: int
    message: str | None
    error: str | None
    pid: int | None
    exit_code: int | None
    peak_rss_mb: float | None
    command: list[Any] | None
    payload: dict[str, Any]
    result: dict[str, Any] | None = None
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None


class CheckOut(BaseModel):
    name: str
    status: Literal["pass", "fail"]
    severity: Literal["blocking", "warning"]
    detail: str
    fix: str | None


class HealthOut(BaseModel):
    status: Literal["ok", "degraded", "fail"]
    checks: list[CheckOut]
    image_licence_warning: str | None = None


class AffectedItem(BaseModel):
    owner_type: Literal["scene", "character"]
    owner_id: str
    kinds: list[str]


class StoryVersionSummary(BaseModel):
    id: str
    version: int
    is_current: bool
    approved_at: datetime | None
    created_at: datetime


class StoryVersionOut(StoryVersionSummary):
    affected: list[AffectedItem] = []


class StoryVersionDetail(StoryVersionOut):
    yaml_text: str


class StoryErrorOut(BaseModel):
    path: str
    message: str
    line: int | None
    column: int | None


class StoryInvalidOut(BaseModel):
    detail: str
    errors: list[StoryErrorOut]


class StaleItem(BaseModel):
    artifact_id: str
    owner_type: str
    owner_id: str
    kind: str


class StaleOut(BaseModel):
    items: list[StaleItem]


class StoryAnswer(BaseModel):
    path: str
    question: str
    answer: str


class StructureRequest(BaseModel):
    storyline: str
    characters: str | None = None
    locations: str | None = None
    product: str | None = None
    dialogue: str | None = None
    style: str | None = None
    language: Literal["hindi", "english", "hinglish"] | None = None
    target_seconds: int = Field(default=12, ge=1, le=60)
    library_picks: list[str] = []
    answers: list[StoryAnswer] = []
