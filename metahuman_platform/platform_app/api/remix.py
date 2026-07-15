from pathlib import Path

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from starlette.concurrency import run_in_threadpool

from platform_app.repositories.role_repository import RoleRepository
from platform_app.repositories.video_repository import VideoRepository
from platform_app.services.background_runner import run_in_background
from platform_app.services.preprocess_service import PreprocessService
from platform_app.services.remix_service import RemixService
from platform_app.services.task_record_delete_service import TaskRecordDeleteService
from platform_app.services.task_query_service import TaskQueryService
from platform_app.settings import get_settings


router = APIRouter(tags=["remix"])


class PreprocessPayload(BaseModel):
    video_id: str


class RemixTaskPayload(BaseModel):
    role_id: str
    source_video_id: str
    prompt_text: str = Field(min_length=1)
    product_doc_text: str = ""
    target_count: int = Field(ge=1)
    is_max_mode: bool = False
    aspect_mode: str = "default"
    resolution: str = "720p"
    subtitle_enabled: bool = True


class BatchDeletePayload(BaseModel):
    role_id: str
    ids: list[str] = Field(default_factory=list)


def build_preprocess_service():
    settings = get_settings()
    return PreprocessService(
        db_path=settings.database_path,
        temp_dir=settings.temp_dir,
        work_dir=settings.work_dir,
    )


def build_remix_service(preprocess_service: PreprocessService):
    settings = get_settings()
    return RemixService(
        db_path=settings.database_path,
        temp_dir=settings.temp_dir,
        generated_dir=settings.generated_dir,
        preprocess_service=preprocess_service,
    )


def build_task_record_delete_service():
    settings = get_settings()
    return TaskRecordDeleteService(db_path=settings.database_path)


@router.get("/api/roles/{role_id}/remix/videos")
async def list_remix_videos(role_id: str):
    settings = get_settings()
    if RoleRepository(settings.database_path).get(role_id) is None:
        raise HTTPException(status_code=404, detail="角色不存在")
    return {"items": VideoRepository(settings.database_path).list_by_role(role_id)}


@router.post("/api/remix/preprocess")
async def start_preprocess(payload: PreprocessPayload):
    try:
        service = build_preprocess_service()
        result = service.start_preprocess(payload.video_id)
        if result["started"]:
            run_in_background(service.run_job, result["job"]["id"])
        return result
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/api/remix/preprocess-jobs")
async def list_preprocess_jobs(role_id: str | None = None):
    settings = get_settings()
    service = TaskQueryService(db_path=settings.database_path)
    return {
        "items": service.list_preprocess_jobs(role_id=role_id),
        "asr_records": service.list_asr_records(role_id=role_id),
    }


@router.post("/api/remix/preprocess-jobs/{job_id}/cancel")
async def cancel_preprocess_job(job_id: str):
    try:
        return build_preprocess_service().cancel_job(job_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.delete("/api/remix/preprocess-jobs/{job_id}")
async def delete_preprocess_job(job_id: str, role_id: str):
    try:
        return await run_in_threadpool(
            build_task_record_delete_service().delete_preprocess_job_record,
            job_id,
            role_id=role_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/api/remix/preprocess-jobs/batch-delete")
async def batch_delete_preprocess_jobs(payload: BatchDeletePayload):
    service = build_task_record_delete_service()
    return await run_in_threadpool(
        service.batch_delete_preprocess_job_records,
        role_id=payload.role_id,
        job_ids=payload.ids,
    )


@router.post("/api/remix/tasks")
async def create_remix_task(payload: RemixTaskPayload):
    preprocess_service = build_preprocess_service()
    service = build_remix_service(preprocess_service)
    task = service.create_task(
        role_id=payload.role_id,
        source_video_id=payload.source_video_id,
        prompt_text=payload.prompt_text,
        product_doc_path=payload.product_doc_text,
        target_count=payload.target_count,
        is_max_mode=payload.is_max_mode,
        aspect_mode=payload.aspect_mode,
        resolution=payload.resolution,
        subtitle_enabled=payload.subtitle_enabled,
    )
    run_in_background(service.run_task, task["id"])
    return task


@router.get("/api/remix/tasks")
async def list_remix_tasks(role_id: str | None = None):
    settings = get_settings()
    preprocess_service = build_preprocess_service()
    remix_service = build_remix_service(preprocess_service)
    tasks = await run_in_threadpool(remix_service.list_tasks)
    if role_id is not None:
        tasks = [task for task in tasks if task["role_id"] == role_id]

    role_cache = {role["id"]: role for role in RoleRepository(settings.database_path).list()}
    video_cache = {video["id"]: video for video in VideoRepository(settings.database_path).list_all()}
    for task in tasks:
        video = video_cache.get(task["source_video_id"], {})
        task["role_name"] = role_cache.get(task["role_id"], {}).get("name", "-")
        task["video_title"] = video.get("title", task["source_video_id"][:8])
    smart_clip_tasks = TaskQueryService(db_path=settings.database_path).list_smart_clip_tasks(role_id=role_id)
    items = [*tasks, *smart_clip_tasks]
    items.sort(key=lambda item: str(item.get("created_at") or item.get("updated_at") or ""), reverse=True)
    return {"items": items}


@router.get("/api/remix/tasks/{task_id}")
async def get_remix_task(task_id: str):
    preprocess_service = build_preprocess_service()
    service = build_remix_service(preprocess_service)
    detail = await run_in_threadpool(service.get_task_detail, task_id)
    if detail["task"] is None:
        raise HTTPException(status_code=404, detail="混剪任务不存在")
    return detail


@router.post("/api/remix/tasks/{task_id}/poll")
async def poll_remix_task(task_id: str):
    preprocess_service = build_preprocess_service()
    service = build_remix_service(preprocess_service)
    detail = await run_in_threadpool(service.get_task_detail, task_id)
    if detail["task"] is None:
        raise HTTPException(status_code=404, detail="混剪任务不存在")
    return detail


@router.post("/api/remix/tasks/{task_id}/cancel")
async def cancel_remix_task(task_id: str):
    preprocess_service = build_preprocess_service()
    service = build_remix_service(preprocess_service)
    detail = await run_in_threadpool(service.get_task_detail, task_id)
    if detail["task"] is None:
        raise HTTPException(status_code=404, detail="混剪任务不存在")
    return await run_in_threadpool(service.cancel_task, task_id)


@router.delete("/api/remix/tasks/{task_id}")
async def delete_remix_task(task_id: str, role_id: str):
    try:
        return await run_in_threadpool(
            build_task_record_delete_service().delete_remix_task_record,
            task_id,
            role_id=role_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/api/remix/tasks/batch-delete")
async def batch_delete_remix_tasks(payload: BatchDeletePayload):
    service = build_task_record_delete_service()
    return await run_in_threadpool(
        service.batch_delete_remix_task_records,
        role_id=payload.role_id,
        task_ids=payload.ids,
    )
