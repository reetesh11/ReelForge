"""Request and response models for the HTTP API."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from reelforge.story.schema import Cue, CueTime

StageName = Literal[
    "DRAFT",
    "STORY_APPROVED",
    "CAST_APPROVED",
    "VOICES_APPROVED",
    "FRAMES_APPROVED",
    "SHOTS_APPROVED",
    "REEL_EXPORTED",
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


class EmotionClipOut(BaseModel):
    url: str
    transcript: str
    clip_seconds: float | None = None


class VoiceOut(BaseModel):
    mode: Literal["preset", "cloned", "recorded"]
    model: Literal["omnivoice", "kokoro"] | None
    voice_id: str | None
    reference_url: str | None = None
    reference_text: str
    speed: float
    language: str
    clip_seconds: float | None = None
    emotion_clips: dict[str, EmotionClipOut] | None = None
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


class CastSetAgeRequest(BaseModel):
    age: Any = None  # checked by `check_age`, which gives the 422 message


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
    age: int | None = None
    age_band: str | None = None
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
    age: int | None = None
    age_band: str | None = None
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


class VoiceGenerateRequest(BaseModel):
    mode: Literal["missing", "stale", "lines"] = "missing"
    lines: list[str] | None = None


class VoiceSelectTakeRequest(BaseModel):
    take_id: str


class VoiceEditTextRequest(BaseModel):
    text: str


class VoiceSetEmotionRequest(BaseModel):
    emotion: str | None = None


class VoiceClipFromTakeRequest(BaseModel):
    scene_id: str
    take_id: str
    transcript: str | None = None


class VoiceSettingsOut(BaseModel):
    phrase_gap_ms: int
    default_phrase_gap_ms: int


class VoiceSettingsPut(BaseModel):
    phrase_gap_ms: int


class VoiceTimingRequest(BaseModel):
    speed: float | None = None
    pause_before: float | None = None
    pause_after: float | None = None


class VoiceLineActionOut(BaseModel):
    project_stage: StageName
    approved_count: int
    total: int
    line: dict[str, Any]
    message: str | None = None


class VoiceShortenOut(BaseModel):
    proposal: str


class FrameCharacterOut(BaseModel):
    key: str
    name: str


class FrameMasterOut(BaseModel):
    key: str
    name: str
    artifact_id: str


class FrameSecondCharacter(BaseModel):
    master_name: str
    other_name: str


class FrameNotes(BaseModel):
    second_character: FrameSecondCharacter | None = None
    product: Literal["included", "missing"] | None = None
    waiting_for_previous_shot: bool | None = None
    needs_master: str | None = None
    no_character: bool | None = None


class FrameTakeOut(BaseModel):
    id: str
    take_no: int
    seed: int
    active: bool
    approved: bool
    stale: bool
    source: Literal["render", "upload"]
    image_url: str
    inputs: list[str]


class FrameCard(BaseModel):
    """Documentation model: responses are plain dicts with empty keys omitted."""

    scene_id: str
    position: int
    characters: list[FrameCharacterOut]
    master: FrameMasterOut | None
    framing: Literal["wide", "medium", "closeup"]
    state: Literal[
        "no_frame",
        "queued",
        "rendering",
        "ready",
        "approved",
        "stale",
        "failed",
        "continue_previous",
    ]
    message: str | None = None
    prompt: str
    prompt_source: Literal["llm", "user", ""]
    look_removed: bool
    takes: list[FrameTakeOut]
    notes: FrameNotes
    continue_previous: bool
    job: JobOut | None


class FramesOut(BaseModel):
    stage: StageName
    approved_count: int
    total: int
    stale_count: int
    jobs: list[JobOut]
    frames: list[FrameCard]


class FrameActionOut(BaseModel):
    project_stage: StageName
    approved_count: int
    total: int
    frame: FrameCard
    job: JobOut | None = None


class SkippedItem(BaseModel):
    scene_id: str
    reason: str


class FramesGenerateRequest(BaseModel):
    mode: Literal["missing", "stale", "scenes"] = "missing"
    scenes: list[str] | None = None


class FramesGenerateOut(BaseModel):
    jobs: list[JobOut]
    skipped: list[SkippedItem]


class FramesCancelOut(BaseModel):
    cancelled: int


class FrameSetFramingRequest(BaseModel):
    framing: Literal["wide", "medium", "closeup"]


class FrameSavePromptRequest(BaseModel):
    prompt: str
    regenerate: bool = False


class FrameContinueRequest(BaseModel):
    enabled: bool


class ShotTakeOut(BaseModel):
    id: str
    take_no: int
    seed: int
    active: bool
    approved: bool
    stale: bool
    source: Literal["render", "upload"]
    quality: Literal["draft", "final"]
    video_url: str
    last_frame_id: str | None
    inputs: list[str]


class ShotCard(BaseModel):
    """Documentation model: responses are plain dicts with empty keys omitted."""

    scene_id: str
    position: int
    shot_type: Literal["talking", "action", "continue"]
    shot_type_auto: Literal["talking", "action", "continue"]
    quality: Literal["draft", "final"]
    width: int
    height: int
    frames: int
    shot_length_s: float
    motion_prompt: str
    state: Literal["no_shot", "queued", "rendering", "ready", "approved", "stale", "failed"]
    message: str | None = None
    oom: bool | None = None
    can_retry_draft: bool | None = None
    blockers: list[Literal["frame_not_approved", "voice_not_approved", "waiting_previous"]]
    frame_url: str | None
    takes: list[ShotTakeOut]
    job: JobOut | None


class ShotEngineOut(BaseModel):
    ok: bool
    message: str


class QueueRow(BaseModel):
    job_id: str
    scene_id: str
    position: int
    shot_type: Literal["talking", "action", "continue"]
    quality: Literal["draft", "final"]
    width: int
    height: int
    status: Literal["queued", "running"]
    estimate_s: int
    estimate_text: str
    can_move: bool


class QueueRunning(BaseModel):
    scene_id: str
    index: int
    total: int
    elapsed_s: int


class QueueOut(BaseModel):
    paused: bool
    rows: list[QueueRow]
    total_shots: int
    total_s: int
    total_text: str
    running: QueueRunning | None


class ShotsOut(BaseModel):
    stage: StageName
    engine: ShotEngineOut
    approved_count: int
    total: int
    stale_count: int
    shots: list[ShotCard]
    queue: QueueOut


class ShotActionOut(BaseModel):
    project_stage: StageName
    approved_count: int
    total: int
    shot: ShotCard
    job: JobOut | None = None


class ShotsRenderAllRequest(BaseModel):
    mode: Literal["missing", "stale"] = "missing"


class ShotsRenderAllOut(BaseModel):
    jobs: list[JobOut]
    skipped: list[SkippedItem]


class ShotSetTypeRequest(BaseModel):
    shot_type: Literal["talking", "action", "continue"]


class ShotSetQualityRequest(BaseModel):
    quality: Literal["draft", "final"]


class ShotSavePromptRequest(BaseModel):
    prompt: str
    rerender: bool = False


class QueueMoveRequest(BaseModel):
    job_id: str
    direction: Literal["up", "down"]


class AssemblyTakeOut(BaseModel):
    id: str
    take_no: int
    active: bool
    video_url: str


class AssemblyShotOut(BaseModel):
    scene_id: str
    takes: list[AssemblyTakeOut]


class PreviewStateOut(BaseModel):
    state: Literal["none", "up_to_date", "out_of_date", "pending", "rebuilding", "failed"]
    step: str | None = None
    progress: int | None = None
    url: str | None = None
    job_id: str | None = None
    error: str | None = None
    rebuild_in_s: float | None = None


class ExportStateOut(BaseModel):
    state: Literal["idle", "running", "failed"]
    step: str | None = None
    step_index: int | None = None
    step_total: int | None = None
    progress: int | None = None
    job_id: str | None = None
    failed_step: str | None = None
    error: str | None = None


class ReelVersionOut(BaseModel):
    version: int
    label: str
    reel_url: str
    cover_url: str
    created_at: str
    missing: bool


class LicenceWarningOut(BaseModel):
    model: str
    version: str
    licence: str


class CaptionPresetOut(BaseModel):
    id: str
    label: str


class AssemblyOut(BaseModel):
    stage: StageName
    blocked_reason: str | None
    edl: dict[str, Any] | None
    edl_hash: str | None
    shots: list[AssemblyShotOut]
    caption_status: dict[str, Literal["words", "line", "pending"]]
    preview: PreviewStateOut
    export: ExportStateOut
    versions: list[ReelVersionOut]
    licence_warnings: list[LicenceWarningOut]
    caption_presets: list[CaptionPresetOut]


class AssemblyBuildRequest(BaseModel):
    force: bool = False


class AssemblyEditRequest(BaseModel):
    op: Literal[
        "reorder",
        "trim",
        "swap_take",
        "set_transition",
        "nudge_dialogue",
        "set_caption_text",
        "set_caption_style",
    ]
    scene_ids: list[str] | None = None
    scene_id: str | None = None
    in_s: float | None = None
    out_s: float | None = None
    take_id: str | None = None
    seconds: float | None = None
    offset_s: float | None = None
    text: str | None = None
    style: str | None = None


class AssemblyEditOut(BaseModel):
    assembly: AssemblyOut
    notes: list[str]


class AssemblyExportRequest(BaseModel):
    accept_licence_warning: bool = False


class AssemblyOpenVersionRequest(BaseModel):
    version: int


# ---- sound cues ----------------------------------------------------------------------------


class AudioEngineOut(BaseModel):
    ok: bool
    message: str


class AudioSettingsOut(BaseModel):
    duck_db: float
    attack_s: float
    release_s: float
    silence_fade_s: float


class AudioSettingsRequest(BaseModel):
    duck_db: float | None = Field(default=None, ge=0, le=40)
    attack_s: float | None = Field(default=None, ge=0)
    release_s: float | None = Field(default=None, ge=0)
    silence_fade_s: float | None = Field(default=None, ge=0)


class AudioTakeOut(BaseModel):
    id: str
    take_no: int
    seed: int
    model: str
    prompt: str
    duration_s: float
    url: str
    picked: bool
    stale: bool


class CueOut(BaseModel):
    id: str
    kind: str
    order: int
    state: Literal["suggested", "draft", "ready", "stale"]
    start: CueTime
    end: CueTime | None = None
    duration: float | None = None
    prompt: str | None = None
    source: str
    gain_db: float | None = None
    fade_in_s: float | None = None
    fade_out_s: float | None = None
    duck: bool | None = None
    start_s: float
    end_s: float
    duration_s: float
    licence: str
    file_name: str | None = None
    picked_take_id: str | None
    takes: list[AudioTakeOut]
    job: JobOut | None
    flags: list[Literal["ends_after_reel"]] | None = None


class AudioOut(BaseModel):
    engine: AudioEngineOut
    legacy_music_hint: bool | None = None
    settings: AudioSettingsOut
    skipped_count: int | None = None
    cues: list[CueOut]


class AudioMoveRequest(BaseModel):
    direction: Literal["up", "down"]


__all__ = ["Cue"]
