from __future__ import annotations

from pathlib import Path

from platform_app.infra.minio_client import MinioObjectStorage
from platform_app.settings import get_settings


class AiTransformStorage:
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

    def assert_inputs_exist(self, input_asset_keys: dict[str, str], required_fields: list[str]):
        missing = []
        for field in required_fields:
            object_key = str(input_asset_keys.get(field) or "").strip()
            if not object_key or not self.storage.object_exists(object_key):
                missing.append(field)
        if missing:
            raise ValueError(f"素材不存在或尚未上传: {', '.join(missing)}")

    def download_inputs(self, *, task_id: str, input_asset_keys: dict[str, str]) -> dict[str, Path]:
        target_dir = self.settings.temp_dir / "ai_transforms" / task_id / "input"
        target_dir.mkdir(parents=True, exist_ok=True)
        local_paths: dict[str, Path] = {}
        for field, object_key in input_asset_keys.items():
            suffix = Path(object_key).suffix
            target_path = target_dir / f"{field}{suffix}"
            local_paths[field] = self.storage.download_file(object_key, target_path)
        return local_paths

    def upload_result(self, *, task_id: str, source_path: str | Path, operation: str = "replace_background") -> str:
        object_key = f"ai-transforms/{task_id}/output/{operation}-result.mp4"
        return self.storage.upload_file(object_key, source_path, content_type="video/mp4")

    def result_download_url(self, result_key: str) -> str:
        if not result_key:
            return ""
        return self.storage.presigned_get_url(result_key)
