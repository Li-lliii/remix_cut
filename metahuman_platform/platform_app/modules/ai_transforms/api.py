from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from platform_app.modules.ai_transforms.schemas import AiTransformCreatePayload, AiTransformSubmitPayload
from platform_app.modules.ai_transforms.service import AiTransformService
from platform_app.settings import get_settings


router = APIRouter(prefix="/api/ai-transforms", tags=["ai-transforms"])


def build_service() -> AiTransformService:
    settings = get_settings()
    return AiTransformService(db_path=settings.database_path)


@router.post("/tasks")
def create_task(payload: AiTransformCreatePayload):
    try:
        return build_service().create_task(
            role_id=payload.role_id,
            source_video_id=payload.source_video_id,
            operations=payload.operations,
            input_asset_keys=payload.input_asset_keys,
            params=payload.params,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/tasks/submit")
def submit_task(payload: AiTransformSubmitPayload):
    try:
        return build_service().submit_task(payload.task_id)
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/tasks")
def list_tasks(role_id: str | None = Query(default=None)):
    return build_service().list_tasks(role_id=role_id)


@router.get("/tasks/{task_id}")
def get_task(task_id: str):
    try:
        return build_service().get_task_detail(task_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/tasks/{task_id}/cancel")
def cancel_task(task_id: str):
    try:
        return build_service().cancel_task(task_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.delete("/tasks/{task_id}")
def delete_task(task_id: str, role_id: str):
    try:
        return build_service().delete_task(task_id, role_id=role_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
