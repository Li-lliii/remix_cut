from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import shutil
import uuid

from platform_app.infra.minio_client import MinioObjectStorage
from platform_app.settings import get_settings


@dataclass(frozen=True)
class UploadObjectSpec:
    field: str
    filename: str
    content_type: str = "application/octet-stream"


class DigitalHumanStorage:
    def __init__(self, *, storage: MinioObjectStorage | None = None):
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

    def build_input_key(self, *, digital_human_id: str, task_id: str, field: str, filename: str) -> str:
        suffix = Path(filename).suffix
        safe_suffix = suffix if suffix else ""
        return f"digital-humans/{digital_human_id}/tasks/{task_id}/input/{field}{safe_suffix}"

    def build_result_key(self, *, digital_human_id: str, task_id: str, filename: str = "result.mp4") -> str:
        return f"digital-humans/{digital_human_id}/tasks/{task_id}/output/{filename}"

    def build_asset_key(self, *, digital_human_id: str, asset_type: str, filename: str) -> str:
        suffix = Path(filename).suffix
        safe_suffix = suffix if suffix else ""
        return f"digital-humans/{digital_human_id}/assets/{asset_type}{safe_suffix}"

    def build_archive_asset_key(
        self,
        *,
        digital_human_id: str,
        asset_type: str,
        upload_id: str,
        filename: str,
    ) -> str:
        suffix = Path(filename).suffix
        safe_suffix = suffix if suffix else ""
        return f"digital-humans/{digital_human_id}/archive/{asset_type}/{upload_id}/source{safe_suffix}"

    def create_presigned_uploads(
        self,
        *,
        digital_human_id: str,
        task_id: str,
        files: list[UploadObjectSpec],
    ) -> tuple[dict[str, str], list[dict]]:
        input_keys: dict[str, str] = {}
        uploads: list[dict] = []
        for file_spec in files:
            object_key = self.build_input_key(
                digital_human_id=digital_human_id,
                task_id=task_id,
                field=file_spec.field,
                filename=file_spec.filename,
            )
            input_keys[file_spec.field] = object_key
            uploads.append(
                {
                    "field": file_spec.field,
                    "object_key": object_key,
                    "upload_url": self.storage.presigned_put_url(
                        object_key,
                        content_type=file_spec.content_type,
                    ),
                    "content_type": file_spec.content_type,
                }
            )
        return input_keys, uploads

    def assert_objects_uploaded(self, input_keys: dict[str, str]):
        missing = [field for field, object_key in input_keys.items() if not self.storage.object_exists(object_key)]
        if missing:
            raise ValueError(f"素材尚未上传完成: {', '.join(missing)}")

    def result_download_url(self, result_key: str) -> str:
        if not result_key:
            return ""
        return self.storage.presigned_get_url(result_key)

    def download_inputs(self, *, task_id: str, input_keys: dict[str, str]) -> dict[str, Path]:
        target_dir = self.settings.temp_dir / "digital_humans" / task_id / "input"
        target_dir.mkdir(parents=True, exist_ok=True)
        local_paths: dict[str, Path] = {}
        for field, object_key in input_keys.items():
            suffix = Path(object_key).suffix
            target_path = target_dir / f"{field}{suffix}"
            local_paths[field] = self.storage.download_file(object_key, target_path)
        return local_paths

    def download_asset(self, *, storage_key: str, target_path: str | Path) -> Path:
        return self.storage.download_file(storage_key, target_path)

    def upload_result(self, *, digital_human_id: str, task_id: str, source_path: str | Path) -> str:
        object_key = self.build_result_key(digital_human_id=digital_human_id, task_id=task_id)
        return self.storage.upload_file(object_key, source_path, content_type="video/mp4")

    def upload_asset_bytes(
        self,
        *,
        digital_human_id: str,
        asset_type: str,
        filename: str,
        content: bytes,
        content_type: str,
    ) -> str:
        object_key = self.build_asset_key(
            digital_human_id=digital_human_id,
            asset_type=asset_type,
            filename=filename,
        )
        return self.storage.upload_bytes(object_key, content, content_type=content_type)

    def upload_archive_asset_bytes(
        self,
        *,
        digital_human_id: str,
        asset_type: str,
        upload_id: str,
        filename: str,
        content: bytes,
        content_type: str,
    ) -> str:
        object_key = self.build_archive_asset_key(
            digital_human_id=digital_human_id,
            asset_type=asset_type,
            upload_id=upload_id,
            filename=filename,
        )
        return self.storage.upload_bytes(object_key, content, content_type=content_type)

    def make_mock_result(self, *, task_id: str, input_paths: dict[str, Path]) -> Path:
        source = input_paths.get("source_video") or input_paths.get("talking_video")
        if source is None:
            raise ValueError("缺少可作为 mock 输出的源视频")
        target_dir = self.settings.temp_dir / "digital_humans" / task_id / "output"
        target_dir.mkdir(parents=True, exist_ok=True)
        target = target_dir / f"result-{uuid.uuid4().hex[:8]}.mp4"
        shutil.copyfile(source, target)
        return target
