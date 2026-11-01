"""Story routes: versions, import/export, approve, stale, schema."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Request, Response
from fastapi.responses import JSONResponse

from reelforge.api.routes_projects import project_out
from reelforge.api.schemas import (
    AffectedItem,
    ProjectOut,
    StaleItem,
    StaleOut,
    StoryInvalidOut,
    StoryVersionDetail,
    StoryVersionOut,
    StoryVersionSummary,
)
from reelforge.context import AppContext
from reelforge.db.models import Project, StoryVersion
from reelforge.story import service
from reelforge.story.errors import StoryError, StoryInvalid
from reelforge.story.schema import story_json_schema


def _invalid(errors: list[StoryError]) -> JSONResponse:
    return JSONResponse(
        status_code=422,
        content={
            "detail": "story.yaml is invalid",
            "errors": [e.model_dump() for e in errors],
        },
    )


def _summary(v: StoryVersion) -> StoryVersionSummary:
    return StoryVersionSummary(
        id=v.id,
        version=v.version,
        is_current=v.is_current,
        approved_at=v.approved_at,
        created_at=v.created_at,
    )


def version_out(saved: service.SavedVersion) -> StoryVersionOut:
    return StoryVersionOut(
        id=saved.id,
        version=saved.version,
        is_current=saved.is_current,
        approved_at=saved.approved_at,
        created_at=saved.created_at,
        affected=[
            AffectedItem(owner_type=a.owner_type, owner_id=a.owner_id, kinds=a.kinds)  # type: ignore[arg-type]
            for a in saved.affected
        ],
    )


def _detail(v: StoryVersion) -> StoryVersionDetail:
    return StoryVersionDetail(**_summary(v).model_dump(), yaml_text=v.yaml_text)


def build_router(ctx: AppContext) -> APIRouter:
    router = APIRouter(prefix="/api/v1", tags=["story"])

    def require_project(project_id: str) -> None:
        with ctx.session_factory() as s:
            if s.get(Project, project_id) is None:
                raise HTTPException(404, "project not found")

    async def read_text(request: Request) -> str:
        body = await request.body()
        if len(body) > service.MAX_STORY_BYTES:
            raise HTTPException(413, "story.yaml is larger than 1 MB")
        try:
            return body.decode("utf-8")
        except UnicodeDecodeError:
            raise StoryInvalid(
                [StoryError(path="", message="story.yaml must be UTF-8 text")]
            ) from None

    async def save(project_id: str, request: Request) -> StoryVersionOut | JSONResponse:
        require_project(project_id)
        try:
            text = await read_text(request)
            return version_out(service.save_version(ctx, project_id, text))
        except StoryInvalid as exc:
            return _invalid(exc.errors)

    @router.put(
        "/projects/{project_id}/story",
        response_model=StoryVersionOut,
        responses={422: {"model": StoryInvalidOut}},
    )
    async def put_story(project_id: str, request: Request) -> Any:
        return await save(project_id, request)

    @router.post(
        "/projects/{project_id}/story:import",
        status_code=201,
        response_model=StoryVersionOut,
        responses={422: {"model": StoryInvalidOut}},
    )
    async def import_story(project_id: str, request: Request) -> Any:
        return await save(project_id, request)

    @router.get("/projects/{project_id}/story")
    async def get_story(project_id: str) -> StoryVersionDetail:
        require_project(project_id)
        current = service.current_version(ctx, project_id)
        if current is None:
            raise HTTPException(404, "no story yet")
        return _detail(current)

    @router.get("/projects/{project_id}/story/versions")
    async def list_versions(project_id: str) -> list[StoryVersionSummary]:
        require_project(project_id)
        return [_summary(v) for v in service.list_versions(ctx, project_id)]

    @router.get("/projects/{project_id}/story/versions/{number}")
    async def get_version(project_id: str, number: int) -> StoryVersionDetail:
        require_project(project_id)
        row = service.get_version(ctx, project_id, number)
        if row is None:
            raise HTTPException(404, "version not found")
        return _detail(row)

    @router.get("/projects/{project_id}/story/export", response_class=Response)
    async def export_story(project_id: str) -> Response:
        require_project(project_id)
        current = service.current_version(ctx, project_id)
        if current is None:
            raise HTTPException(404, "no story yet")
        return Response(content=current.yaml_text.encode("utf-8"), media_type="application/yaml")

    @router.post("/projects/{project_id}/story:approve")
    async def approve_story(project_id: str) -> ProjectOut:
        require_project(project_id)
        try:
            return project_out(service.approve(ctx, project_id))
        except service.NoStory:
            raise HTTPException(409, "There is no story to approve yet.") from None
        except service.StructuringRunning:
            raise HTTPException(409, "A structuring job is running.") from None

    @router.get("/projects/{project_id}/stale")
    async def stale(project_id: str) -> StaleOut:
        require_project(project_id)
        return StaleOut(
            items=[
                StaleItem(
                    artifact_id=i.artifact_id,
                    owner_type=i.owner_type,
                    owner_id=i.owner_id,
                    kind=i.kind,
                )
                for i in service.stale_items(ctx, project_id)
            ]
        )

    @router.get("/story/schema")
    async def story_schema() -> dict[str, Any]:
        return story_json_schema()

    return router
