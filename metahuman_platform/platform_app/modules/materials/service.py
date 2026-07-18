from __future__ import annotations

import shutil
import uuid
from pathlib import Path

from platform_app.infra.minio_client import MinioObjectStorage
from platform_app.modules.materials.constants import (
    ASSET_TYPE_AUDIO,
    ASSET_TYPE_IMAGE,
    ASSET_TYPE_VIDEO,
    BACKGROUND_IMAGE_PARTITION,
    DIGITAL_HUMAN_CREATION_PARTITION,
    ORIGINAL_VIDEO_PARTITION,
    VISIBILITY_PUBLIC,
)
from platform_app.modules.materials.repository import MaterialAssetRepository
from platform_app.settings import get_settings
from platform_app.services.asr_adapter import infer_aspect_ratio, probe_duration


def _owner_segment(*, visibility: str, owner_user_id: str = "", owner_role_id: str = "") -> str:
    if visibility == VISIBILITY_PUBLIC:
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
        return self.save_video_asset(
            filename=filename,
            content=content,
            partition_name=ORIGINAL_VIDEO_PARTITION,
            owner_user_id=owner_user_id,
            owner_role_id=owner_role_id,
            visibility=visibility,
            source_type=source_type,
            title=title,
            tags=tags,
            metadata=metadata,
        )

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
        return self.save_image_asset(
            filename=filename,
            content=content,
            partition_name=BACKGROUND_IMAGE_PARTITION,
            owner_user_id=owner_user_id,
            visibility=visibility,
            source_type=source_type,
            title=title,
            tags=tags,
            metadata=metadata,
        )

    def save_digital_human_video(
        self,
        *,
        filename: str,
        content: bytes,
        owner_user_id: str = "",
        visibility: str = "private",
        title: str = "",
        tags: list[str] | None = None,
        metadata: dict | None = None,
    ):
        return self.save_video_asset(
            filename=filename,
            content=content,
            partition_name=DIGITAL_HUMAN_CREATION_PARTITION,
            owner_user_id=owner_user_id,
            visibility=visibility,
            source_type="platform_builtin" if visibility == VISIBILITY_PUBLIC else "user_upload",
            title=title,
            tags=tags,
            metadata={"source": "digital_human_material_upload", **(metadata or {})},
        )

    def save_digital_human_image(
        self,
        *,
        filename: str,
        content: bytes,
        owner_user_id: str = "",
        visibility: str = "private",
        title: str = "",
        tags: list[str] | None = None,
        metadata: dict | None = None,
    ):
        return self.save_image_asset(
            filename=filename,
            content=content,
            partition_name=DIGITAL_HUMAN_CREATION_PARTITION,
            owner_user_id=owner_user_id,
            visibility=visibility,
            source_type="platform_builtin" if visibility == VISIBILITY_PUBLIC else "user_upload",
            title=title,
            tags=tags,
            metadata={"source": "digital_human_material_upload", **(metadata or {})},
        )

    def save_digital_human_audio(
        self,
        *,
        filename: str,
        content: bytes,
        owner_user_id: str = "",
        visibility: str = "private",
        title: str = "",
        tags: list[str] | None = None,
        metadata: dict | None = None,
    ):
        return self.save_audio_asset(
            filename=filename,
            content=content,
            partition_name=DIGITAL_HUMAN_CREATION_PARTITION,
            owner_user_id=owner_user_id,
            visibility=visibility,
            source_type="platform_builtin" if visibility == VISIBILITY_PUBLIC else "user_upload",
            title=title,
            tags=tags,
            metadata={"source": "digital_human_material_upload", **(metadata or {})},
        )

    def save_video_asset(
        self,
        *,
        filename: str,
        content: bytes,
        partition_name: str,
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
        return self._save_file_asset(
            asset_type=ASSET_TYPE_VIDEO,
            partition_name=partition_name,
            filename=filename,
            content=content,
            default_extension=".mp4",
            content_type="video/mp4",
            owner_user_id=owner_user_id,
            owner_role_id=owner_role_id,
            visibility=visibility,
            source_type=source_type,
            title=title,
            tags=tags,
            metadata=metadata,
            probe_video=True,
        )

    def save_image_asset(
        self,
        *,
        filename: str,
        content: bytes,
        partition_name: str,
        owner_user_id: str = "",
        visibility: str = "private",
        source_type: str = "user_upload",
        title: str = "",
        tags: list[str] | None = None,
        metadata: dict | None = None,
    ):
        if not content:
            raise ValueError("图片文件为空")
        extension = _safe_extension(filename, ".png")
        return self._save_file_asset(
            asset_type=ASSET_TYPE_IMAGE,
            partition_name=partition_name,
            filename=filename,
            content=content,
            default_extension=".png",
            content_type=self._image_content_type(extension),
            owner_user_id=owner_user_id,
            visibility=visibility,
            source_type=source_type,
            title=title,
            tags=tags,
            metadata=metadata,
            probe_image=True,
        )

    def save_audio_asset(
        self,
        *,
        filename: str,
        content: bytes,
        partition_name: str,
        owner_user_id: str = "",
        visibility: str = "private",
        source_type: str = "user_upload",
        title: str = "",
        tags: list[str] | None = None,
        metadata: dict | None = None,
    ):
        if not content:
            raise ValueError("音频文件为空")
        extension = _safe_extension(filename, ".mp3")
        return self._save_file_asset(
            asset_type=ASSET_TYPE_AUDIO,
            partition_name=partition_name,
            filename=filename,
            content=content,
            default_extension=".mp3",
            content_type=self._audio_content_type(extension),
            owner_user_id=owner_user_id,
            visibility=visibility,
            source_type=source_type,
            title=title,
            tags=tags,
            metadata=metadata,
        )

    def _save_file_asset(
        self,
        *,
        asset_type: str,
        partition_name: str,
        filename: str,
        content: bytes,
        default_extension: str,
        content_type: str,
        owner_user_id: str = "",
        owner_role_id: str = "",
        visibility: str = "private",
        source_type: str = "user_upload",
        title: str = "",
        tags: list[str] | None = None,
        metadata: dict | None = None,
        probe_video: bool = False,
        probe_image: bool = False,
    ):
        asset_id = str(uuid.uuid4())
        extension = _safe_extension(filename, default_extension)
        owner = _owner_segment(visibility=visibility, owner_user_id=owner_user_id, owner_role_id=owner_role_id)
        if partition_name in {ORIGINAL_VIDEO_PARTITION, BACKGROUND_IMAGE_PARTITION}:
            object_key = f"materials/{partition_name}/{visibility}/{owner}/{asset_id}/source{extension}"
        else:
            object_key = f"materials/{partition_name}/{asset_type}/{visibility}/{owner}/{asset_id}/source{extension}"
        temp_dir = self.uploads_dir / "materials" / "_incoming" / asset_id
        try:
            temp_dir.mkdir(parents=True, exist_ok=True)
            file_path = temp_dir / f"source{extension}"
            file_path.write_bytes(content)
            duration_sec = probe_duration(file_path) if probe_video else 0.0
            aspect_ratio = infer_aspect_ratio(file_path) if probe_video else "unknown"
            width, height = self._probe_image_size(file_path) if probe_image else (0, 0)
            self.storage.upload_file(object_key, file_path, content_type=content_type)
            return self.repository.create(
                asset_id=asset_id,
                asset_type=asset_type,
                partition_name=partition_name,
                source_type=source_type,
                visibility=visibility,
                owner_user_id=owner_user_id,
                owner_role_id=owner_role_id,
                title=title or filename,
                filename=filename,
                file_path=f"minio://{self.settings.minio_bucket}/{object_key}",
                content_type=content_type,
                storage_backend="minio",
                storage_key=object_key,
                duration_sec=duration_sec,
                aspect_ratio=aspect_ratio,
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

    def _audio_content_type(self, extension: str) -> str:
        normalized = extension.lower()
        if normalized == ".wav":
            return "audio/wav"
        if normalized == ".m4a":
            return "audio/mp4"
        if normalized == ".aac":
            return "audio/aac"
        if normalized == ".ogg":
            return "audio/ogg"
        return "audio/mpeg"
