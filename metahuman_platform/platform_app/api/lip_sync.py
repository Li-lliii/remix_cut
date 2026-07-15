from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from starlette.concurrency import run_in_threadpool

from platform_app.repositories.lip_sync_repository import (
    LipSyncProjectRepository,
    ScriptCandidateRepository,
)
from platform_app.repositories.role_repository import RoleRepository
from platform_app.repositories.video_repository import VideoRepository
from platform_app.services.lip_sync_service import LipSyncService
from platform_app.services.task_record_delete_service import TaskRecordDeleteService
from platform_app.services.task_query_service import TaskQueryService
from platform_app.settings import get_settings


router = APIRouter(tags=["lip-sync"])


class LipSyncProjectPayload(BaseModel):
    role_id: str
    base_video_id: str
    prompt_text: str = Field(min_length=1)
    product_doc_text: str = ""


class GenerateScriptsPayload(BaseModel):
    count: int = Field(default=3, ge=1, le=5)


class EditScriptPayload(BaseModel):
    edited_content: str = Field(min_length=1)


class SelectScriptPayload(BaseModel):
    script_id: str


class LipSyncTaskPayload(BaseModel):
    project_id: str
    selected_script_id: str
    aspect_mode: str = "default"
    resolution: str = "720p"
    subtitle_enabled: bool = True


class BatchDeletePayload(BaseModel):
    role_id: str
    ids: list[str] = Field(default_factory=list)


def build_lip_sync_service():
    settings = get_settings()
    return LipSyncService(
        db_path=settings.database_path,
        temp_dir=settings.temp_dir,
        generated_dir=settings.generated_dir,
    )


def build_task_record_delete_service():
    settings = get_settings()
    return TaskRecordDeleteService(db_path=settings.database_path)


def _get_lip_sync_service():
    return build_lip_sync_service()


@router.get("/api/roles/{role_id}/lip-sync/videos")
async def list_lip_sync_videos(role_id: str):
    settings = get_settings()
    if RoleRepository(settings.database_path).get(role_id) is None:
        raise HTTPException(status_code=404, detail="角色不存在")
    items = VideoRepository(settings.database_path).list_by_role(role_id)
    for item in items:
        item["selectable"] = float(item.get("duration_sec") or 0) <= 30.0
    return {"items": items}


@router.post("/api/lip-sync/projects")
async def create_lip_sync_project(payload: LipSyncProjectPayload):
    try:
        return await run_in_threadpool(
            build_lip_sync_service().create_project,
            role_id=payload.role_id,
            base_video_id=payload.base_video_id,
            prompt_text=payload.prompt_text,
            product_doc_path=payload.product_doc_text,
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/api/lip-sync/projects/{project_id}")
async def get_lip_sync_project(project_id: str):
    settings = get_settings()
    project_repository = LipSyncProjectRepository(settings.database_path)
    candidate_repository = ScriptCandidateRepository(settings.database_path)
    project = project_repository.get_project(project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="对口型项目不存在")
    return {
        "project": project,
        "candidates": candidate_repository.list_candidates(project_id),
    }


@router.post("/api/lip-sync/projects/{project_id}/scripts/generate")
async def generate_lip_sync_scripts(project_id: str, payload: GenerateScriptsPayload):
    try:
        return await run_in_threadpool(
            build_lip_sync_service().generate_candidates,
            project_id,
            count=payload.count,
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/api/lip-sync/projects/{project_id}/scripts/{script_id}/regenerate")
async def regenerate_lip_sync_script(project_id: str, script_id: str):
    try:
        return await run_in_threadpool(
            build_lip_sync_service().regenerate_candidate,
            project_id,
            script_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/api/lip-sync/projects/{project_id}/scripts/{script_id}/edit")
async def edit_lip_sync_script(project_id: str, script_id: str, payload: EditScriptPayload):
    del project_id
    try:
        return await run_in_threadpool(
            build_lip_sync_service().edit_candidate,
            script_id,
            edited_content=payload.edited_content,
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/api/lip-sync/projects/{project_id}/select-script")
async def select_lip_sync_script(project_id: str, payload: SelectScriptPayload):
    try:
        return await run_in_threadpool(
            build_lip_sync_service().select_candidate,
            project_id,
            payload.script_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/api/lip-sync/tasks")
async def create_lip_sync_task(payload: LipSyncTaskPayload):
    try:
        task = await run_in_threadpool(
            build_lip_sync_service().create_task,
            project_id=payload.project_id,
            selected_script_id=payload.selected_script_id,
            aspect_mode=payload.aspect_mode,
            resolution=payload.resolution,
            subtitle_enabled=payload.subtitle_enabled,
        )
        return task
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/api/lip-sync/tasks")
async def list_lip_sync_tasks(role_id: str | None = None):
    settings = get_settings()
    service = TaskQueryService(db_path=settings.database_path)
    return {"items": service.list_lip_sync_tasks(role_id=role_id)}


@router.get("/api/lip-sync/tasks/{task_id}")
async def get_lip_sync_task(task_id: str):
    try:
        service = _get_lip_sync_service()
        detail = await run_in_threadpool(
            service.get_task_detail,
            task_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    task = detail["task"]
    if task is None:
        raise HTTPException(status_code=404, detail="对口型任务不存在")
    return {"task": task}


@router.post("/api/lip-sync/tasks/{task_id}/poll")
async def poll_lip_sync_task(task_id: str):
    try:
        service = _get_lip_sync_service()
        detail = await run_in_threadpool(
            service.get_task_detail,
            task_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    task = detail["task"]
    if task is None:
        raise HTTPException(status_code=404, detail="对口型任务不存在")
    return {"task": task}


@router.post("/api/lip-sync/tasks/{task_id}/cancel")
async def cancel_lip_sync_task(task_id: str):
    try:
        return await run_in_threadpool(
            build_lip_sync_service().cancel_task,
            task_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.delete("/api/lip-sync/tasks/{task_id}")
async def delete_lip_sync_task(task_id: str, role_id: str):
    try:
        return await run_in_threadpool(
            build_task_record_delete_service().delete_lip_sync_task_record,
            task_id,
            role_id=role_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/api/lip-sync/tasks/batch-delete")
async def batch_delete_lip_sync_tasks(payload: BatchDeletePayload):
    service = build_task_record_delete_service()
    return await run_in_threadpool(
        service.batch_delete_lip_sync_task_records,
        role_id=payload.role_id,
        task_ids=payload.ids,
    )
