from __future__ import annotations

from fastapi import APIRouter, File, HTTPException, UploadFile

from platform_app.modules.digital_humans.archive_service import DigitalHumanArchiveService
from platform_app.settings import get_settings


router = APIRouter(prefix="/api/digital-human-archive", tags=["digital-human-archive"])


def build_service() -> DigitalHumanArchiveService:
    settings = get_settings()
    db_ref = (
        settings.database_url
        if settings.database_url.startswith(("postgresql://", "postgresql+"))
        else settings.database_path
    )
    return DigitalHumanArchiveService(db_path=db_ref)


async def _read_upload(upload: UploadFile, default_filename: str):
    content = await upload.read()
    return (
        upload.filename or default_filename,
        content,
        upload.content_type or "application/octet-stream",
    )


def _business_error_status(message: str) -> int:
    if "不存在" in message:
        return 404
    return 400


@router.get("")
def list_digital_human_archives():
    return build_service().list_archives()


@router.get("/{digital_human_id}")
def get_digital_human_archive(digital_human_id: str):
    try:
        return build_service().get_archive_detail(digital_human_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/{digital_human_id}/source-video/upload")
async def upload_source_video(
    digital_human_id: str,
    video: UploadFile = File(..., description="数字人原始视频"),
):
    filename, content, content_type = await _read_upload(video, "source_video.mp4")
    try:
        return build_service().upload_source_video(
            digital_human_id=digital_human_id,
            filename=filename,
            content=content,
            content_type=content_type,
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=_business_error_status(str(exc)), detail=str(exc)) from exc


@router.post("/{digital_human_id}/source-audio/upload")
async def upload_source_audio(
    digital_human_id: str,
    audio: UploadFile = File(..., description="数字人原始音频"),
):
    filename, content, content_type = await _read_upload(audio, "source_audio.wav")
    try:
        return build_service().upload_source_audio(
            digital_human_id=digital_human_id,
            filename=filename,
            content=content,
            content_type=content_type,
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=_business_error_status(str(exc)), detail=str(exc)) from exc


@router.post("/{digital_human_id}/source-image/upload")
async def upload_source_image(
    digital_human_id: str,
    image: UploadFile = File(..., description="数字人人物/参考图片"),
):
    filename, content, content_type = await _read_upload(image, "source_image.png")
    try:
        return build_service().upload_source_image(
            digital_human_id=digital_human_id,
            filename=filename,
            content=content,
            content_type=content_type,
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=_business_error_status(str(exc)), detail=str(exc)) from exc
