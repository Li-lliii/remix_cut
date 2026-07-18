from __future__ import annotations

from fastapi import APIRouter, File, Form, HTTPException, UploadFile

from platform_app.modules.digital_humans.create_service import DigitalHumanCreateService
from platform_app.settings import get_settings


router = APIRouter(prefix="/api/digital-humans", tags=["digital-human-create"])


def build_service() -> DigitalHumanCreateService:
    settings = get_settings()
    db_ref = (
        settings.database_url
        if settings.database_url.startswith(("postgresql://", "postgresql+"))
        else settings.database_path
    )
    return DigitalHumanCreateService(
        db_path=db_ref,
        uploads_dir=settings.uploads_dir,
    )


async def _read_optional_upload(upload: UploadFile | None):
    if upload is None or not upload.filename:
        return None
    content = await upload.read()
    if not content:
        return None
    return (
        upload.filename,
        content,
        upload.content_type or "application/octet-stream",
    )


@router.post("/create-avatar")
@router.post("/create-from-materials")
async def create_digital_human_avatar(
    talking_video: UploadFile | None = File(default=None, description="口播视频，建议 3-5 分钟，MP4/MOV/AVI"),
    person_image: UploadFile | None = File(default=None, description="人物图片，可选"),
    voice_sample: UploadFile | None = File(default=None, description="声音样本，可选"),
    talking_video_material_id: str = Form("", description="平台素材库中的视频素材 ID"),
    person_image_material_id: str = Form("", description="平台素材库中的图片素材 ID"),
    voice_sample_material_id: str = Form("", description="平台素材库中的音频素材 ID"),
    name: str = Form(..., description="数字人名称"),
    avatar_type: str = Form(..., description="形象类型"),
    gender: str = Form("", description="性别"),
    department: str = Form(..., description="所属科室/部门"),
    organization: str = Form("", description="归属机构/医院"),
    speaker_name: str = Form("", description="主讲人/人员姓名"),
    tags: str = Form("", description="标签，逗号分隔"),
    style: str = Form("", description="形象风格"),
    description: str = Form("", description="个人简介/形象描述"),
):
    video_upload = await _read_optional_upload(talking_video)
    try:
        return build_service().create_avatar_training_task(
            name=name,
            avatar_type=avatar_type,
            gender=gender,
            department=department,
            organization=organization,
            speaker_name=speaker_name,
            tags=tags,
            style=style,
            description=description,
            talking_video=video_upload,
            person_image=await _read_optional_upload(person_image),
            voice_sample=await _read_optional_upload(voice_sample),
            talking_video_material_id=talking_video_material_id.strip(),
            person_image_material_id=person_image_material_id.strip(),
            voice_sample_material_id=voice_sample_material_id.strip(),
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
