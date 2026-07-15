import mimetypes

from fastapi import APIRouter, File, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field, field_validator

from platform_app.repositories.role_repository import RoleRepository
from platform_app.services.role_deletion_service import RoleDeletionService
from platform_app.settings import get_settings


router = APIRouter(prefix="/api/roles", tags=["roles"])


class RoleCreatePayload(BaseModel):
    name: str = Field(min_length=1)
    description: str = ""
    tags: list[str] = Field(default_factory=list)
    avatar_url: str = ""

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("角色名称必填")
        return value


@router.get("")
async def list_roles(search: str | None = Query(default=None)):
    settings = get_settings()
    repository = RoleRepository(settings.database_path)
    return {"items": repository.list(search=search)}


@router.post("")
async def create_role(payload: RoleCreatePayload):
    settings = get_settings()
    repository = RoleRepository(settings.database_path)
    return repository.create(
        name=payload.name,
        description=payload.description.strip(),
        tags=payload.tags,
        avatar_url=payload.avatar_url.strip(),
    )


@router.get("/{role_id}")
async def get_role(role_id: str):
    settings = get_settings()
    repository = RoleRepository(settings.database_path)
    role = repository.get(role_id)
    if role is None:
        raise HTTPException(status_code=404, detail="角色不存在")
    return role


@router.delete("/{role_id}")
async def delete_role(role_id: str):
    settings = get_settings()
    service = RoleDeletionService(
        db_path=settings.database_path,
        uploads_dir=settings.uploads_dir,
        temp_dir=settings.temp_dir,
        generated_dir=settings.generated_dir,
    )
    try:
        return service.delete_role(role_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/{role_id}/cover")
async def upload_role_cover(role_id: str, cover: UploadFile = File(...)):
    settings = get_settings()
    repository = RoleRepository(settings.database_path)
    role = repository.get(role_id)
    if role is None:
        raise HTTPException(status_code=404, detail="角色不存在")
    if not cover.content_type or not cover.content_type.startswith("image/"):
        raise HTTPException(status_code=400, detail="只允许上传图片")

    content = await cover.read()
    if not content:
        raise HTTPException(status_code=400, detail="封面文件为空")

    cover_dir = settings.uploads_dir / "roles" / role_id / "cover"
    cover_dir.mkdir(parents=True, exist_ok=True)
    for old_file in cover_dir.glob("cover.*"):
        if old_file.is_file():
            old_file.unlink()

    suffix = mimetypes.guess_extension(cover.content_type, strict=False) or ".png"
    file_path = cover_dir / f"cover{suffix}"
    file_path.write_bytes(content)

    return repository.update_avatar(role_id, f"/api/roles/{role_id}/cover")


@router.get("/{role_id}/cover")
async def get_role_cover(role_id: str):
    settings = get_settings()
    repository = RoleRepository(settings.database_path)
    role = repository.get(role_id)
    if role is None:
        raise HTTPException(status_code=404, detail="角色不存在")

    cover_dir = settings.uploads_dir / "roles" / role_id / "cover"
    if not cover_dir.exists():
        raise HTTPException(status_code=404, detail="角色封面不存在")

    cover_files = sorted(
        [path for path in cover_dir.glob("cover.*") if path.is_file()],
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )
    if not cover_files:
        raise HTTPException(status_code=404, detail="角色封面不存在")

    file_path = cover_files[0]
    media_type = mimetypes.guess_type(file_path.name)[0] or "image/png"
    return FileResponse(path=file_path, filename=file_path.name, media_type=media_type)
