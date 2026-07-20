from __future__ import annotations

import json

from fastapi import APIRouter, File, Form, HTTPException, Query, UploadFile

from platform_app.modules.ai_transforms.schemas import AiTransformCreatePayload, AiTransformSubmitPayload
from platform_app.modules.ai_transforms.service import AiTransformService
from platform_app.settings import get_settings


router = APIRouter(prefix="/api/ai-transforms", tags=["ai-transforms"])


def build_service() -> AiTransformService:
    settings = get_settings()
    return AiTransformService(db_path=settings.database_path)


def _parse_json_form(value: str, *, field_name: str):
    try:
        return json.loads(value)
    except json.JSONDecodeError as exc:
        raise ValueError(f"{field_name} 必须是合法 JSON") from exc


def _parse_operations(value: str) -> list[str]:
    parsed = _parse_json_form(value, field_name="operations")
    if not isinstance(parsed, list):
        raise ValueError("operations 必须是 JSON 数组")
    return [str(item) for item in parsed]


@router.get("/capabilities")
def list_capabilities():
    return build_service().list_capabilities()


@router.post("/source-videos/upload")
async def upload_source_video(
    role_id: str = Form(...),
    source_video: UploadFile = File(...),
):
    try:
        return build_service().upload_source_video(
            role_id=role_id,
            filename=source_video.filename or "source.mp4",
            content=await source_video.read(),
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


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


@router.post("/tasks/upload-and-run")
async def upload_and_run_task(
    role_id: str = Form(...),
    source_video_id: str = Form(...),
    operations: str = Form(default='["replace_background"]'),
    params: str = Form(default="{}"),
    owner_user_id: str = Form(default=""),
    background_image: UploadFile | None = File(default=None),
    clothes_image: UploadFile | None = File(default=None),
    avatar_reference: UploadFile | None = File(default=None),
    speech_audio: UploadFile | None = File(default=None),
    speech_text: str = Form(default=""),
    product_image: UploadFile | None = File(default=None),
):
    del clothes_image, avatar_reference, speech_audio, speech_text, product_image
    try:
        parsed_operations = _parse_operations(operations)
        parsed_params = _parse_json_form(params, field_name="params")
        if not isinstance(parsed_params, dict):
            raise ValueError("params 必须是 JSON 对象")
        background_image_content = await background_image.read() if background_image is not None else None
        return build_service().upload_and_run(
            role_id=role_id,
            source_video_id=source_video_id,
            operations=parsed_operations,
            background_image_filename=background_image.filename if background_image is not None else None,
            background_image_content=background_image_content,
            owner_user_id=owner_user_id,
            params=parsed_params,
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
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
