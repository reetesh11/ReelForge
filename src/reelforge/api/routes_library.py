"""Library routes: character records and master images."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse, JSONResponse

from reelforge.api.schemas import LibraryCharacterOut, LibraryCreate, LibraryPatch
from reelforge.context import AppContext
from reelforge.library import service

PATCH_ERROR = "Only name, aliases and tags can be changed."


def build_router(ctx: AppContext) -> APIRouter:
    router = APIRouter(prefix="/api/v1/library", tags=["library"])

    @router.get("/characters", response_model=list[LibraryCharacterOut])
    async def list_characters() -> JSONResponse:
        return JSONResponse([service.record(ctx, c) for c in service.list_all(ctx)])

    @router.post("/characters", status_code=201, response_model=LibraryCharacterOut)
    async def create_character(body: LibraryCreate) -> JSONResponse:
        try:
            ch = service.create(ctx, **body.model_dump())
        except service.ArtifactNotFound:
            raise HTTPException(404, "artifact not found") from None
        return JSONResponse(service.record(ctx, ch), status_code=201)

    @router.get("/characters/{cid}", response_model=LibraryCharacterOut)
    async def get_character(cid: str) -> JSONResponse:
        ch = service.get(ctx, cid)
        if ch is None:
            raise HTTPException(404, "character not found")
        return JSONResponse(service.record(ctx, ch))

    @router.patch("/characters/{cid}", response_model=LibraryCharacterOut)
    async def patch_character(cid: str, body: LibraryPatch) -> JSONResponse:
        if body.model_extra:
            raise HTTPException(400, PATCH_ERROR)
        changes = body.model_dump(exclude_unset=True, exclude_none=True)
        try:
            ch = service.patch(ctx, cid, changes)
        except service.CharacterNotFound:
            raise HTTPException(404, "character not found") from None
        return JSONResponse(service.record(ctx, ch))

    @router.get("/characters/{cid}/master")
    async def get_master(cid: str) -> FileResponse:
        ch = service.get(ctx, cid)
        found = service.master_file(ctx, ch) if ch is not None else None
        if found is None:
            raise HTTPException(404, "master image not found")
        return FileResponse(found[0], media_type=found[1])

    @router.get("/characters/{cid}/voice-reference")
    async def get_voice_reference(cid: str) -> FileResponse:
        path = service.voice_reference_file(ctx, cid)
        if path is None:
            raise HTTPException(404, "voice reference not found")
        return FileResponse(path)

    return router
