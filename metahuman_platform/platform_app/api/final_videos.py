import mimetypes

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from fastapi.responses import FileResponse
from starlette.concurrency import run_in_threadpool

from platform_app.services.final_video_service import FinalVideoService
from platform_app.settings import get_settings


router = APIRouter(tags=["final-videos"])


class FinalVideoDeleteItem(BaseModel):
    id: str
    source_type: str


class FinalVideoBatchDeletePayload(BaseModel):
    role_id: str
    items: list[FinalVideoDeleteItem] = Field(default_factory=list)


@router.get("/api/final-videos")
async def list_final_videos(role_id: str | None = None, q: str | None = None, source_type: str | None = None):
    settings = get_settings()
    service = FinalVideoService(db_path=settings.database_path)
    items = await run_in_threadpool(
        service.list_final_videos,
        role_id=role_id,
        q=q,
        source_type=source_type,
    )
    return {"items": items}


@router.delete("/api/final-videos/{item_id}")
async def delete_final_video(item_id: str, role_id: str, source_type: str):
    settings = get_settings()
    service = FinalVideoService(db_path=settings.database_path)
    try:
        return await run_in_threadpool(
            service.delete_final_video,
            item_id=item_id,
            source_type=source_type,
            role_id=role_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/api/final-videos/batch-delete")
async def batch_delete_final_videos(payload: FinalVideoBatchDeletePayload):
    settings = get_settings()
    service = FinalVideoService(db_path=settings.database_path)
    return await run_in_threadpool(
        service.batch_delete_final_videos,
        role_id=payload.role_id,
        items=[item.model_dump() for item in payload.items],
    )


@router.get("/api/final-videos/{item_id}/stream")
async def stream_final_video(item_id: str, source_type: str):
    settings = get_settings()
    service = FinalVideoService(db_path=settings.database_path)
    file_path = await run_in_threadpool(
        service.get_output_video_path,
        item_id=item_id,
        source_type=source_type,
    )
    if file_path is None:
        raise HTTPException(status_code=404, detail="成片不存在")
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="成片文件不存在")
    media_type = mimetypes.guess_type(file_path.name)[0] or "application/octet-stream"
    return FileResponse(path=file_path, filename=file_path.name, media_type=media_type)
