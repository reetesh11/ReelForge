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


class VoiceOut(BaseModel):
    mode: Literal["preset", "cloned", "recorded"]
    model: Literal["omnivoice", "kokoro"] | None
    voice_id: str | None
    reference_url: str | None = None
    reference_text: str
    speed: float
    language: str
    clip_seconds: float | None = None
    model_mismatch: bool


class LibraryCharacterOut(BaseModel):
    """Documentation model: responses are plain dicts with empty keys omitted."""

    id: str
    name: str
    aliases: list[str]
    look_text: str
    master_image_url: str | None = None
    master_sha256: str | None = None
    seed: int | None = None
    model: str | None = None
    model_id: str | None = None
    created_at: str
    tags: list[str]
    voice_reference: str
    license: str | None = None
    license_url: str | None = None
    parent_character_id: str | None = None
    voice: VoiceOut | None = None


class LibraryCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    aliases: list[str] = []
    look_text: str
    tags: list[str] = []
    seed: int | None = None
    voice_reference: str = ""
    master_artifact_id: str | None = None


class LibraryPatch(BaseModel):
    """Only name, aliases and tags; any other key is rejected with 400 by the route."""

    model_config = ConfigDict(extra="allow")

    name: str | None = Field(default=None, min_length=1, max_length=200)
    aliases: list[str] | None = None
    tags: list[str] | None = None


class CastRefine(BaseModel):
    from_candidate: str
    instruction: str = ""


class CastGenerateRequest(BaseModel):
    look_text: str | None = None
    seed: int | None = None
    regenerate: bool = False
    refine: CastRefine | None = None
    backend: Literal["draw_things", "mflux"] | None = None


class CastApproveRequest(BaseModel):
    candidate_id: str


class CastUseLibraryRequest(BaseModel):
    character_id: str


class CastCandidateOut(BaseModel):
    id: str
    kind: Literal["generated", "refine", "upload"]
    prompt: str
    seed: int
    model: str
    model_key: str
    license: str | None = None
    license_url: str | None = None
    image_url: str
    width: int | None
    height: int | None


class CastProgressOut(BaseModel):
    completed: int
    total: int
    elapsed_s: float
    message: str


class CastItemOut(BaseModel):
    key: str
    name: str
    aliases: list[str]
    look: str
    bible_line: str
    bible_source: Literal["llm", "user", "raw", ""]
    note: str | None = None
    state: Literal["empty", "generating", "ready", "approved", "failed", "stopped"]
    job_id: str | None = None
    progress: CastProgressOut | None = None
    error: str | None = None
    candidates: list[CastCandidateOut]
    approved: bool
    master_artifact_id: str | None = None
    master_sha256: str | None = None
    seed: int | None = None
    voice_reference: str
    library_character_id: str | None = None
    variant_of_library_id: str | None = None


class CastBackendOut(BaseModel):
    kind: Literal["mock", "draw_things"]
    reachable: bool
    port: int
    mflux_available: bool


class CastOut(BaseModel):
    stage: StageName
    approved_count: int
    total: int
    image_backend: CastBackendOut
    licence_warning: str | None = None
    characters: list[CastItemOut]


class CastActionOut(BaseModel):
    project_stage: StageName
    approved_count: int
    total: int
    character: CastItemOut


class VoiceModelChoice(BaseModel):
    key: str
    label: str


class VoiceModelOut(BaseModel):
    voice_model: Literal["omnivoice", "kokoro"]
    label: str
    model_id: str
    choices: list[VoiceModelChoice]


class VoiceModelPut(BaseModel):
    voice_model: str


class VoiceSetRequest(BaseModel):
    mode: Literal["preset", "cloned", "recorded"]
    voice_id: str | None = None
    reference_text: str | None = None
    speed: float | None = None


class VoiceClearOut(BaseModel):
    voice: None = None


class VoiceModelInUse(BaseModel):
    key: str
    label: str
    model_id: str


class VoicePresetOut(BaseModel):
    id: str
    label: str


class VoiceCharacterOut(BaseModel):
    key: str
    name: str
    avatar_url: str | None = None
    voice: VoiceOut | None


class VoicesOut(BaseModel):
    """Documentation model: responses are plain dicts with empty keys omitted."""

    stage: StageName
    voice_model: VoiceModelInUse
    presets: list[VoicePresetOut]
    approved_count: int
    total: int
    stale_count: int
    characters: list[VoiceCharacterOut]
    lines: list[dict[str, Any]]
    job: JobOut | None
