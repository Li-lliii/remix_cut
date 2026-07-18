from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import FileResponse, RedirectResponse

from platform_app.modules.digital_humans.repository import DigitalHumanAssetRepository
from platform_app.modules.digital_humans.schemas import (
    DigitalHumanEditTaskCreatePayload,
    DigitalHumanObjectTaskCreatePayload,
    DigitalHumanTaskSubmitPayload,
)
from platform_app.modules.digital_humans.service import DigitalHumanService
from platform_app.modules.digital_humans.storage import UploadObjectSpec
from platform_app.settings import get_settings


router = APIRouter(prefix="/api/digital-humans", tags=["digital-humans"])


def build_service() -> DigitalHumanService:
    settings = get_settings()
    db_ref = (
        settings.database_url
        if settings.database_url.startswith(("postgresql://", "postgresql+"))
        else settings.database_path
    )
    return DigitalHumanService(
        db_path=db_ref,
        uploads_dir=settings.uploads_dir,
    )


@router.get("")
def list_digital_humans(
    search: str | None = Query(default=None, description="按名称、科室、机构、讲者、标签、简介搜索"),
    keyword: str | None = Query(default=None, description="search 的兼容别名"),
    avatar_type: str | None = Query(default=None, description="形象类型筛选，例如 real/anime"),
    type_filter: str | None = Query(default=None, alias="type", description="avatar_type 的兼容别名"),
    status: str | None = Query(default=None, description="状态筛选，支持 active/training/failed 或原始状态"),
):
    return build_service().list_digital_human_library(
        search=search or keyword,
        avatar_type=avatar_type or type_filter,
        status=status,
    )


@router.get("/{digital_human_id}")
def get_digital_human(digital_human_id: str):
    try:
        return build_service().get_digital_human_detail(digital_human_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/object-upload-tasks")
def create_object_upload_task(payload: DigitalHumanObjectTaskCreatePayload):
    try:
        return build_service().create_object_upload_task(
            digital_human_id=payload.digital_human_id,
            task_type=payload.task_type,
            workflow_name=payload.workflow_name,
            prompt_text=payload.prompt_text,
            files=[
                UploadObjectSpec(
                    field=file_spec.field,
                    filename=file_spec.filename,
                    content_type=file_spec.content_type,
                )
                for file_spec in payload.files
            ],
            params=payload.params,
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/{digital_human_id}/outfit-change-tasks")
def create_outfit_change_task(digital_human_id: str, payload: DigitalHumanEditTaskCreatePayload):
    try:
        return build_service().create_object_upload_task(
            digital_human_id=digital_human_id,
            task_type="change_outfit",
            workflow_name="digital_human_change_outfit",
            prompt_text=payload.prompt_text,
            files=[
                UploadObjectSpec(
                    field="source_video",
                    filename=payload.source_video_filename,
                    content_type=payload.source_video_content_type,
                ),
                UploadObjectSpec(
                    field="outfit_image",
                    filename=payload.reference_filename,
                    content_type=payload.reference_content_type,
                ),
            ],
            params=payload.params,
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/{digital_human_id}/background-change-tasks")
def create_background_change_task(digital_human_id: str, payload: DigitalHumanEditTaskCreatePayload):
    try:
        return build_service().create_object_upload_task(
            digital_human_id=digital_human_id,
            task_type="change_background",
            workflow_name="digital_human_change_background",
            prompt_text=payload.prompt_text,
            files=[
                UploadObjectSpec(
                    field="source_video",
                    filename=payload.source_video_filename,
                    content_type=payload.source_video_content_type,
                ),
                UploadObjectSpec(
                    field="background_image",
                    filename=payload.reference_filename,
                    content_type=payload.reference_content_type,
                ),
            ],
            params=payload.params,
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/generation-tasks/submit")
def submit_generation_task(payload: DigitalHumanTaskSubmitPayload):
    try:
        return build_service().submit_object_upload_task(payload.task_id)
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/generation-tasks/{task_id}/submit-comfyui")
def submit_avatar_training_to_comfyui(task_id: str):
    try:
        return build_service().submit_avatar_training_to_comfyui(task_id)
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/generation-tasks/{task_id}")
def get_generation_task(task_id: str):
    try:
        return build_service().get_task_with_progress(task_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/assets/{asset_id}/stream")
def stream_digital_human_asset(asset_id: str):
    settings = get_settings()
    db_ref = (
        settings.database_url
        if settings.database_url.startswith(("postgresql://", "postgresql+"))
        else settings.database_path
    )
    asset = DigitalHumanAssetRepository(db_ref).get(asset_id)
    if asset is None:
        raise HTTPException(status_code=404, detail="素材不存在")
    if asset.get("storage_backend") == "minio" and asset.get("storage_key"):
        try:
            return RedirectResponse(build_service().storage.result_download_url(asset["storage_key"]))
        except RuntimeError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc
    file_path = Path(asset["file_path"])
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="素材文件不存在")
    return FileResponse(
        path=file_path,
        filename=asset["filename"],
        media_type=asset.get("content_type") or "application/octet-stream",
    )
