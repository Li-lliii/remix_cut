import mimetypes

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel
from starlette.concurrency import run_in_threadpool

from platform_app.repositories.video_repository import VideoRepository
from platform_app.services.background_runner import run_in_background
from platform_app.services.smart_clip_service import SmartClipService
from platform_app.settings import get_settings


router = APIRouter(tags=["smart-clips"])


class SmartClipProjectCreatePayload(BaseModel):
    source_video_id: str
    force_recreate: bool = False


def build_smart_clip_service():
    settings = get_settings()
    return SmartClipService(
        db_path=settings.database_path,
        temp_dir=settings.temp_dir,
        generated_dir=settings.generated_dir,
    )


@router.post("/api/remix/smart-clips/projects")
async def create_smart_clip_project(payload: SmartClipProjectCreatePayload):
    settings = get_settings()
    video = VideoRepository(settings.database_path).get(payload.source_video_id)
    if video is None:
        raise HTTPException(status_code=404, detail="源视频不存在")
    service = build_smart_clip_service()
    try:
        project, should_process = await run_in_threadpool(
            service.create_or_restart_project,
            role_id=video["role_id"],
            source_video_id=payload.source_video_id,
            force_recreate=payload.force_recreate,
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    detail = await run_in_threadpool(service.get_project_detail, project["id"])
    if should_process:
        run_in_background(service.process_project, project["id"])
    return detail


@router.get("/api/remix/smart-clips/projects/{project_id}")
async def get_smart_clip_project(project_id: str):
    service = build_smart_clip_service()
    try:
        return await run_in_threadpool(service.get_project_detail, project_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/api/remix/smart-clips/projects/{project_id}/candidates")
async def list_smart_clip_candidates(project_id: str):
    service = build_smart_clip_service()
    try:
        return {"items": await run_in_threadpool(service.list_candidates, project_id)}
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.delete("/api/remix/smart-clips/candidates/{candidate_id}")
async def delete_smart_clip_candidate(candidate_id: str):
    service = build_smart_clip_service()
    try:
        return await run_in_threadpool(service.delete_candidate, candidate_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/api/remix/smart-clips/projects/{project_id}/export")
async def export_smart_clip_project(project_id: str):
    service = build_smart_clip_service()
    try:
        detail = await run_in_threadpool(service.start_export, project_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    run_in_background(service.export_project, project_id, assume_started=True)
    return detail


@router.get("/api/remix/smart-clips/projects/{project_id}/candidates/{candidate_id}/stream")
async def stream_smart_clip_candidate(project_id: str, candidate_id: str):
    service = build_smart_clip_service()
    try:
        file_path = await run_in_threadpool(
            service.get_candidate_stream_path,
            project_id=project_id,
            candidate_id=candidate_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    if file_path is None:
        raise HTTPException(status_code=404, detail="候选切片尚未导出")
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="候选切片文件不存在")
    media_type = mimetypes.guess_type(file_path.name)[0] or "application/octet-stream"
    return FileResponse(path=file_path, filename=file_path.name, media_type=media_type)
