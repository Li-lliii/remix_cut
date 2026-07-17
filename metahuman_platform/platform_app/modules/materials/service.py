from __future__ import annotations

import shutil
import uuid
from pathlib import Path

from platform_app.infra.minio_client import MinioObjectStorage
from platform_app.modules.materials.repository import MaterialAssetRepository
from platform_app.settings import get_settings
from platform_app.services.asr_adapter import infer_aspect_ratio, probe_duration


ORIGINAL_VIDEO_PARTITION = "original_videos"
BACKGROUND_IMAGE_PARTITION = "background_images"


def _owner_segment(*, visibility: str, owner_user_id: str = "", owner_role_id: str = "") -> str:
    if visibility == "public":
        return "platform"
    return owner_user_id or owner_role_id or "anonymous"


def _safe_extension(filename: str, default: str) -> str:
    return Path(filename).suffix or default


class MaterialService:
    def __init__(self, *, db_path: Path, uploads_dir: Path, storage: MinioObjectStorage | None = None):
        self.db_path = Path(db_path)
        self.uploads_dir = Path(uploads_dir)
        self.repository = MaterialAssetRepository(self.db_path)
        settings = get_settings()
        self.settings = settings
        self.storage = storage or MinioObjectStorage(
            endpoint=settings.minio_endpoint,
            access_key=settings.minio_access_key,
            secret_key=settings.minio_secret_key,
            bucket=settings.minio_bucket,
            secure=settings.minio_secure,
            presign_expiry_sec=settings.minio_presign_expiry_sec,
        )

    def save_original_video(
        self,
        *,
        filename: str,
        content: bytes,
        owner_user_id: str = "",
        owner_role_id: str = "",
        visibility: str = "private",
        source_type: str = "user_upload",
        title: str = "",
        tags: list[str] | None = None,
        metadata: dict | None = None,
    ):
        if not content:
            raise ValueError("视频文件为空")
        asset_id = str(uuid.uuid4())
        extension = _safe_extension(filename, ".mp4")
        owner = _owner_segment(visibility=visibility, owner_user_id=owner_user_id, owner_role_id=owner_role_id)
        object_key = f"materials/{ORIGINAL_VIDEO_PARTITION}/{visibility}/{owner}/{asset_id}/source{extension}"
        temp_dir = self.uploads_dir / "materials" / "_incoming" / asset_id
        try:
            temp_dir.mkdir(parents=True, exist_ok=True)
            file_path = temp_dir / f"source{extension}"
            file_path.write_bytes(content)
            duration_sec = probe_duration(file_path)
            aspect_ratio = infer_aspect_ratio(file_path)
            self.storage.upload_file(object_key, file_path, content_type="video/mp4")
            return self.repository.create(
                asset_id=asset_id,
                asset_type="video",
                partition_name=ORIGINAL_VIDEO_PARTITION,
                source_type=source_type,
                visibility=visibility,
                owner_user_id=owner_user_id,
                owner_role_id=owner_role_id,
                title=title or filename,
                filename=filename,
                file_path=f"minio://{self.settings.minio_bucket}/{object_key}",
                content_type="video/mp4",
                storage_backend="minio",
                storage_key=object_key,
                duration_sec=duration_sec,
                aspect_ratio=aspect_ratio,
                tags=tags or [],
                metadata=metadata or {},
            )
        except Exception:
            shutil.rmtree(temp_dir, ignore_errors=True)
            raise
        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)

    def save_background_image(
        self,
        *,
        filename: str,
        content: bytes,
        owner_user_id: str = "",
        visibility: str = "private",
        source_type: str = "user_upload",
        title: str = "",
        tags: list[str] | None = None,
        metadata: dict | None = None,
    ):
        if not content:
            raise ValueError("背景图文件为空")
        asset_id = str(uuid.uuid4())
        extension = _safe_extension(filename, ".png")
        owner = _owner_segment(visibility=visibility, owner_user_id=owner_user_id)
        object_key = f"materials/{BACKGROUND_IMAGE_PARTITION}/{visibility}/{owner}/{asset_id}/source{extension}"
        temp_dir = self.uploads_dir / "materials" / "_incoming" / asset_id
        try:
            temp_dir.mkdir(parents=True, exist_ok=True)
            file_path = temp_dir / f"source{extension}"
            file_path.write_bytes(content)
            width, height = self._probe_image_size(file_path)
            self.storage.upload_file(object_key, file_path, content_type=self._image_content_type(extension))
            return self.repository.create(
                asset_id=asset_id,
                asset_type="image",
                partition_name=BACKGROUND_IMAGE_PARTITION,
                source_type=source_type,
                visibility=visibility,
                owner_user_id=owner_user_id,
                title=title or filename,
                filename=filename,
                file_path=f"minio://{self.settings.minio_bucket}/{object_key}",
                content_type=self._image_content_type(extension),
                storage_backend="minio",
                storage_key=object_key,
                width=width,
                height=height,
                tags=tags or [],
                metadata=metadata or {},
            )
        except Exception:
            shutil.rmtree(temp_dir, ignore_errors=True)
            raise
        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)

    def list_assets(
        self,
        *,
        asset_type: str | None = None,
        partition_name: str | None = None,
        scope: str | None = None,
        owner_user_id: str | None = None,
        owner_role_id: str | None = None,
    ):
        if scope == "mine":
            return {
                "items": self.repository.list(
                    asset_type=asset_type,
                    partition_name=partition_name,
                    visibility="private",
                    owner_user_id=owner_user_id or "",
                    owner_role_id=owner_role_id,
                )
            }
        if scope == "public":
            return {
                "items": self.repository.list(
                    asset_type=asset_type,
                    partition_name=partition_name,
                    visibility="public",
                )
            }
        if scope == "available":
            mine = self.repository.list(
                asset_type=asset_type,
                partition_name=partition_name,
                visibility="private",
                owner_user_id=owner_user_id or "",
                owner_role_id=owner_role_id,
            )
            public = self.repository.list(
                asset_type=asset_type,
                partition_name=partition_name,
                visibility="public",
            )
            return {"items": [*mine, *public]}
        return {
            "items": self.repository.list(
                asset_type=asset_type,
                partition_name=partition_name,
                owner_user_id=owner_user_id,
                owner_role_id=owner_role_id,
            )
        }

    def get_asset(self, asset_id: str):
        asset = self.repository.get(asset_id)
        if asset is None:
            raise ValueError("素材不存在")
        return asset

    def result_download_url(self, asset: dict) -> str:
        if asset.get("storage_backend") == "minio" and asset.get("storage_key"):
            return self.storage.presigned_get_url(asset["storage_key"])
        return ""

    def download_asset(self, *, asset_id: str, target_path: str | Path) -> Path:
        asset = self.get_asset(asset_id)
        target = Path(target_path)
        if asset.get("storage_backend") == "minio" and asset.get("storage_key"):
            return self.storage.download_file(asset["storage_key"], target)
        source = Path(asset["file_path"])
        if not source.exists():
            raise FileNotFoundError(f"素材文件不存在: {source}")
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)
        return target

    def _probe_image_size(self, file_path: Path) -> tuple[int, int]:
        try:
            from PIL import Image  # type: ignore

            with Image.open(file_path) as image:
                return int(image.width), int(image.height)
        except Exception:
            return 0, 0

    def _image_content_type(self, extension: str) -> str:
        normalized = extension.lower()
        if normalized in {".jpg", ".jpeg"}:
            return "image/jpeg"
        if normalized == ".webp":
            return "image/webp"
        return "image/png"
