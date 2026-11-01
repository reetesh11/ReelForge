"""SQLAlchemy 2 declarative models (14 tables)."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    TypeDecorator,
)
from sqlalchemy.engine import Dialect
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from reelforge.ids import new_id


def utcnow() -> datetime:
    return datetime.now(UTC)


class UTCDateTime(TypeDecorator[datetime]):
    """Stores UTC datetimes in SQLite and always returns timezone-aware values."""

    impl = DateTime
    cache_ok = True

    def process_bind_param(self, value: datetime | None, dialect: Dialect) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None:
            value = value.replace(tzinfo=UTC)
        return value.astimezone(UTC).replace(tzinfo=None)

    def process_result_value(self, value: datetime | None, dialect: Dialect) -> datetime | None:
        return value.replace(tzinfo=UTC) if value is not None else None


class Base(DeclarativeBase):
    type_annotation_map = {dict[str, Any]: JSON, list[Any]: JSON}


def _pk() -> Mapped[str]:
    return mapped_column(String(26), primary_key=True, default=new_id)


def _created() -> Mapped[datetime]:
    return mapped_column(UTCDateTime, default=utcnow)


class Project(Base):
    __tablename__ = "projects"

    id: Mapped[str] = _pk()
    slug: Mapped[str] = mapped_column(String(120))
    title: Mapped[str] = mapped_column(String(200))
    data_dir: Mapped[str] = mapped_column(Text)
    stage: Mapped[str] = mapped_column(String(32), default="DRAFT", server_default="DRAFT")
    brand_kit_id: Mapped[str | None] = mapped_column(
        ForeignKey("brand_kits.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = _created()
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)


class StoryVersion(Base):
    __tablename__ = "story_versions"

    id: Mapped[str] = _pk()
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"))
    version: Mapped[int] = mapped_column(Integer)
    yaml_text: Mapped[str] = mapped_column(Text, default="")
    is_current: Mapped[bool] = mapped_column(Boolean, default=False)
    approved_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)


class Voice(Base):
    __tablename__ = "voices"

    id: Mapped[str] = _pk()
    mode: Mapped[str] = mapped_column(String(16), default="preset")
    model_key: Mapped[str | None] = mapped_column(String(64), nullable=True)
    voice_ref: Mapped[str | None] = mapped_column(Text, nullable=True)
    reference_artifact_id: Mapped[str | None] = mapped_column(String(26), nullable=True)
    speed: Mapped[float] = mapped_column(Float, default=1.0)
    language: Mapped[str] = mapped_column(String(16), default="hi")


class Character(Base):
    __tablename__ = "characters"

    id: Mapped[str] = _pk()
    name: Mapped[str] = mapped_column(String(200))
    aliases: Mapped[list[Any]] = mapped_column(JSON, default=list)
    look_text: Mapped[str] = mapped_column(Text, default="")
    master_artifact_id: Mapped[str | None] = mapped_column(String(26), nullable=True)
    sheet_artifact_ids: Mapped[list[Any]] = mapped_column(JSON, default=list)
    voice_id: Mapped[str | None] = mapped_column(
        ForeignKey("voices.id", ondelete="SET NULL"), nullable=True
    )
    tags: Mapped[list[Any]] = mapped_column(JSON, default=list)
    parent_character_id: Mapped[str | None] = mapped_column(
        ForeignKey("characters.id", ondelete="SET NULL"), nullable=True
    )


class ProjectCharacter(Base):
    __tablename__ = "project_characters"

    project_id: Mapped[str] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), primary_key=True
    )
    story_key: Mapped[str] = mapped_column(String(64), primary_key=True)
    character_id: Mapped[str] = mapped_column(ForeignKey("characters.id", ondelete="CASCADE"))


class Scene(Base):
    __tablename__ = "scenes"

    id: Mapped[str] = _pk()
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"))
    story_key: Mapped[str] = mapped_column(String(64))
    position: Mapped[int] = mapped_column(Integer)
    shot_type: Mapped[str] = mapped_column(String(32), default="")
    duration_s: Mapped[float] = mapped_column(Float, default=0.0)
    frames: Mapped[int | None] = mapped_column(Integer, nullable=True)
    continue_from: Mapped[str | None] = mapped_column(String(64), nullable=True)


class Line(Base):
    __tablename__ = "lines"

    id: Mapped[str] = _pk()
    scene_id: Mapped[str] = mapped_column(ForeignKey("scenes.id", ondelete="CASCADE"))
    character_id: Mapped[str | None] = mapped_column(
        ForeignKey("characters.id", ondelete="SET NULL"), nullable=True
    )
    text: Mapped[str] = mapped_column(Text, default="")
    language: Mapped[str] = mapped_column(String(16), default="hi")
    speed: Mapped[float] = mapped_column(Float, default=1.0)
    pause_before: Mapped[float] = mapped_column(Float, default=0.0)
    pause_after: Mapped[float] = mapped_column(Float, default=0.0)


class Artifact(Base):
    __tablename__ = "artifacts"
    __table_args__ = (
        Index(
            "ix_artifacts_owner_active", "project_id", "owner_type", "owner_id", "kind", "is_active"
        ),
        Index("ix_artifacts_inputs_fp", "inputs_fp"),
    )

    id: Mapped[str] = _pk()
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"))
    owner_type: Mapped[str] = mapped_column(String(32))
    owner_id: Mapped[str] = mapped_column(String(64))
    kind: Mapped[str] = mapped_column(String(32))
    take_no: Mapped[int] = mapped_column(Integer, default=1)
    path: Mapped[str] = mapped_column(Text)
    sha256: Mapped[str] = mapped_column(String(64))
    inputs_fp: Mapped[str] = mapped_column(String(64))
    prompt: Mapped[str] = mapped_column(Text)
    version: Mapped[str] = mapped_column(String(64))
    params: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    model_key: Mapped[str] = mapped_column(String(64))
    seed: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(16), default="ready")
    is_active: Mapped[bool] = mapped_column(Boolean, default=False)
    duration_s: Mapped[float | None] = mapped_column(Float, nullable=True)
    width: Mapped[int | None] = mapped_column(Integer, nullable=True)
    height: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_by_job: Mapped[str | None] = mapped_column(String(26), nullable=True)
    created_at: Mapped[datetime] = _created()


class ArtifactInput(Base):
    __tablename__ = "artifact_inputs"

    artifact_id: Mapped[str] = mapped_column(
        ForeignKey("artifacts.id", ondelete="CASCADE"), primary_key=True
    )
    input_artifact_id: Mapped[str] = mapped_column(
        ForeignKey("artifacts.id", ondelete="CASCADE"), primary_key=True
    )


class Job(Base):
    __tablename__ = "jobs"
    __table_args__ = (Index("ix_jobs_queue", "status", "priority", "created_at"),)

    id: Mapped[str] = _pk()
    project_id: Mapped[str | None] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), nullable=True
    )
    type: Mapped[str] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(16), default="queued")
    priority: Mapped[int] = mapped_column(Integer, default=0)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    heavy: Mapped[bool] = mapped_column(Boolean, default=False)
    mem_need_gb: Mapped[float] = mapped_column(Float, default=0.0)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    progress: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    message: Mapped[str | None] = mapped_column(Text, nullable=True)
    pid: Mapped[int | None] = mapped_column(Integer, nullable=True)
    command: Mapped[list[Any] | None] = mapped_column(JSON, nullable=True)
    log_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = _created()
    started_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    peak_rss_mb: Mapped[float | None] = mapped_column(Float, nullable=True)
    exit_code: Mapped[int | None] = mapped_column(Integer, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)


class Approval(Base):
    __tablename__ = "approvals"

    id: Mapped[str] = _pk()
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"))
    stage: Mapped[str] = mapped_column(String(32))
    owner_type: Mapped[str | None] = mapped_column(String(32), nullable=True)
    owner_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    artifact_id: Mapped[str | None] = mapped_column(String(26), nullable=True)
    approved_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)


class ReelVersion(Base):
    __tablename__ = "reel_versions"

    id: Mapped[str] = _pk()
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"))
    version: Mapped[int] = mapped_column(Integer)
    edl_artifact_id: Mapped[str | None] = mapped_column(String(26), nullable=True)
    final_artifact_id: Mapped[str | None] = mapped_column(String(26), nullable=True)
    credits: Mapped[list[Any]] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = _created()


class BrandKit(Base):
    __tablename__ = "brand_kits"

    id: Mapped[str] = _pk()
    name: Mapped[str] = mapped_column(String(200))
    data_dir: Mapped[str] = mapped_column(Text, default="")
    config: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)


class Setting(Base):
    __tablename__ = "settings"

    key: Mapped[str] = mapped_column(String(128), primary_key=True)
    value: Mapped[Any] = mapped_column(JSON, nullable=True)
