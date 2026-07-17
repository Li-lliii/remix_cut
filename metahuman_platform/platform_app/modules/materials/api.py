from __future__ import annotations

import mimetypes
from pathlib import Path

from fastapi import APIRouter, File, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse, RedirectResponse

from platform_app.modules.materials.service import BACKGROUND_IMAGE_PARTITION, ORIGINAL_VIDEO_PARTITION, MaterialService
from platform_app.settings import get_settings


router = APIRouter(prefix="/api/materials", tags=["materials"])


def build_service() -> MaterialService:
    settings = get_settings()
    return MaterialService(db_path=settings.database_path, uploads_dir=settings.uploads_dir)


def _parse_tags(raw: str = "") -> list[str]:
    return [item.strip() for item in raw.replace("，", ",").split(",") if item.strip()]


@router.post("/original-videos/upload")
async def upload_original_video(
    video: UploadFile = File(...),
    role_id: str = Query(default="", description="可选，标记该素材来自哪个角色"),
    owner_user_id: str = Query(default="", description="可选，当前用户 ID"),
    visibility: str = Query(default="private", description="private/public"),
    title: str = Query(default="", description="素材展示名称"),
    tags: str = Query(default="", description="逗号分隔标签"),
):
    try:
        content = await video.read()
        return build_service().save_original_video(
            filename=video.filename or "upload.mp4",
            content=content,
            owner_user_id=owner_user_id,
            owner_role_id=role_id,
            visibility=visibility,
            source_type="platform_builtin" if visibility == "public" else "user_upload",
            title=title,
            tags=_parse_tags(tags),
            metadata={"source": "materials_upload"},
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"上传素材失败: {exc}") from exc


@router.post("/background-images/upload")
async def upload_background_image(
    image: UploadFile = File(...),
    owner_user_id: str = Query(default="", description="可选，当前用户 ID"),
    visibility: str = Query(default="private", description="private/public"),
    title: str = Query(default="", description="素材展示名称"),
    tags: str = Query(default="", description="逗号分隔标签"),
):
    try:
        content = await image.read()
        return build_service().save_background_image(
            filename=image.filename or "background.png",
            content=content,
            owner_user_id=owner_user_id,
            visibility=visibility,
            source_type="platform_builtin" if visibility == "public" else "user_upload",
            title=title,
            tags=_parse_tags(tags),
            metadata={"source": "background_image_upload"},
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"上传背景图失败: {exc}") from exc


@router.get("")
def list_materials(
    asset_type: str | None = Query(default=None),
    partition_name: str | None = Query(default=None),
    role_id: str | None = Query(default=None),
    owner_user_id: str | None = Query(default=None),
    scope: str | None = Query(default=None, description="mine/public/available"),
):
    return build_service().list_assets(
        asset_type=asset_type,
        partition_name=partition_name,
        scope=scope,
        owner_user_id=owner_user_id,
        owner_role_id=role_id,
    )


@router.get("/original-videos")
def list_original_videos(
    role_id: str | None = Query(default=None),
    owner_user_id: str | None = Query(default=None),
    scope: str | None = Query(default=None, description="mine/public/available"),
):
    return build_service().list_assets(
        asset_type="video",
        partition_name=ORIGINAL_VIDEO_PARTITION,
        scope=scope,
        owner_user_id=owner_user_id,
        owner_role_id=role_id,
    )


@router.get("/background-images")
def list_background_images(
    owner_user_id: str | None = Query(default=None),
    scope: str | None = Query(default="available", description="mine/public/available"),
):
    return build_service().list_assets(
        asset_type="image",
        partition_name=BACKGROUND_IMAGE_PARTITION,
        scope=scope,
        owner_user_id=owner_user_id,
    )


@router.get("/{asset_id}")
def get_material(asset_id: str):
    try:
        return build_service().get_asset(asset_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/{asset_id}/stream")
def stream_material(asset_id: str):
    service = build_service()
    try:
        asset = service.get_asset(asset_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    if asset.get("storage_backend") == "minio" and asset.get("storage_key"):
        try:
            return RedirectResponse(service.result_download_url(asset))
        except RuntimeError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc
    file_path = Path(asset["file_path"])
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="素材文件不存在")
    media_type = asset.get("content_type") or mimetypes.guess_type(file_path.name)[0] or "application/octet-stream"
    return FileResponse(path=file_path, filename=asset["filename"], media_type=media_type)
