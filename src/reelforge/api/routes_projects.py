"""Project routes."""

from __future__ import annotations

import re
from datetime import UTC, datetime

from fastapi import APIRouter, HTTPException, Response
from sqlalchemy import select

from reelforge.api.schemas import (
    ArtifactBody,
    ArtifactResult,
    ProjectCreate,
    ProjectOut,
    ProjectPatch,
    StagesOut,
)
from reelforge.api.stages import derive_stages, stages_approved
from reelforge.artifacts.service import ArtifactRequest, request_artifact
from reelforge.context import AppContext
from reelforge.db.models import Job, Project, utcnow
from reelforge.ids import new_id

PROJECT_SUBDIRS = ("cast", "voices", "frames", "shots", "assembly", "uploads", "logs")


def slugify(title: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")[:60].strip("-")
    return slug or "project"


def project_out(p: Project) -> ProjectOut:
    return ProjectOut(
        id=p.id,
        slug=p.slug,
        title=p.title,
        data_dir=p.data_dir,
        stage=p.stage,  # type: ignore[arg-type]
        stages_approved=stages_approved(p.stage),
        brand_kit_id=p.brand_kit_id,
        created_at=p.created_at,
        updated_at=p.updated_at,
    )


def build_router(ctx: AppContext) -> APIRouter:
    router = APIRouter(prefix="/api/v1/projects", tags=["projects"])

    def load(project_id: str) -> Project:
        with ctx.session_factory() as s:
            project = s.get(Project, project_id)
        if project is None:
            raise HTTPException(404, "project not found")
        return project

    @router.post("", status_code=201)
    async def create_project(body: ProjectCreate) -> ProjectOut:
        project_id = new_id()
        slug = slugify(body.title)
        data_dir = f"projects/{datetime.now(UTC):%Y-%m-%d}_{slug}_{project_id}"
        root = ctx.settings.data_root / data_dir
        for sub in PROJECT_SUBDIRS:
            (root / sub).mkdir(parents=True, exist_ok=True)
        now = utcnow()
        project = Project(
            id=project_id,
            slug=slug,
            title=body.title,
            data_dir=data_dir,
            stage="DRAFT",
            created_at=now,
            updated_at=now,
        )
        with ctx.session_factory.begin() as s:
            s.add(project)
        return project_out(project)

    @router.get("")
    async def list_projects() -> list[ProjectOut]:
        with ctx.session_factory() as s:
            rows = s.scalars(select(Project).order_by(Project.updated_at.desc(), Project.id.desc()))
            return [project_out(p) for p in rows]

    @router.get("/{project_id}")
    async def get_project(project_id: str) -> ProjectOut:
        return project_out(load(project_id))

    @router.patch("/{project_id}")
    async def patch_project(project_id: str, body: ProjectPatch) -> ProjectOut:
        stage_changed = False
        with ctx.session_factory.begin() as s:
            project = s.get(Project, project_id)
            if project is None:
                raise HTTPException(404, "project not found")
            if body.title is not None:
                project.title = body.title
            if body.stage is not None and body.stage != project.stage:
                project.stage = body.stage
                stage_changed = True
            project.updated_at = utcnow()
            s.flush()
            out = project_out(project)
        if stage_changed:
            ctx.bus.publish("stage.changed", {"project_id": project_id, "stage": out.stage})
        return out

    @router.delete("/{project_id}", status_code=204)
    async def delete_project(project_id: str) -> Response:
        with ctx.session_factory.begin() as s:
            project = s.get(Project, project_id)
            if project is None:
                raise HTTPException(404, "project not found")
            s.delete(project)
        return Response(status_code=204)

    @router.get("/{project_id}/stages")
    async def get_stages(project_id: str) -> StagesOut:
        project = load(project_id)
        with ctx.session_factory() as s:
            jobs = list(s.scalars(select(Job).where(Job.project_id == project_id)))
        return StagesOut(stages=derive_stages(project.stage, jobs))

    @router.post("/{project_id}/artifacts", status_code=202)
    async def post_artifact(project_id: str, body: ArtifactBody) -> ArtifactResult:
        load(project_id)
        req = ArtifactRequest(project_id=project_id, **body.model_dump())
        result = request_artifact(ctx, req)
        return ArtifactResult(
            cache_hit=result.cache_hit,
            artifact_id=result.artifact.id if result.artifact else None,
            job_id=result.job.id if result.job else None,
        )

    return router
