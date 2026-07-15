from __future__ import annotations

from datetime import timedelta
from io import BytesIO
from pathlib import Path


class MinioObjectStorage:
    def __init__(
        self,
        *,
        endpoint: str,
        access_key: str,
        secret_key: str,
        bucket: str,
        secure: bool = False,
        presign_expiry_sec: int = 3600,
    ):
        self.endpoint = endpoint
        self.access_key = access_key
        self.secret_key = secret_key
        self.bucket = bucket
        self.secure = secure
        self.presign_expiry_sec = presign_expiry_sec
        self._client = None

    def _get_client(self):
        if self._client is not None:
            return self._client
        try:
            from minio import Minio  # type: ignore
        except ModuleNotFoundError as exc:
            raise RuntimeError("minio 依赖未安装，无法使用 MinIO 对象存储") from exc
        self._client = Minio(
            self.endpoint,
            access_key=self.access_key,
            secret_key=self.secret_key,
            secure=self.secure,
        )
        return self._client

    def presigned_put_url(self, object_key: str, *, content_type: str | None = None) -> str:
        del content_type
        return self._get_client().presigned_put_object(
            self.bucket,
            object_key,
            expires=timedelta(seconds=self.presign_expiry_sec),
        )

    def presigned_get_url(self, object_key: str) -> str:
        return self._get_client().presigned_get_object(
            self.bucket,
            object_key,
            expires=timedelta(seconds=self.presign_expiry_sec),
        )

    def object_exists(self, object_key: str) -> bool:
        try:
            self._get_client().stat_object(self.bucket, object_key)
            return True
        except Exception:
            return False

    def download_file(self, object_key: str, target_path: str | Path) -> Path:
        target = Path(target_path)
        target.parent.mkdir(parents=True, exist_ok=True)
        self._get_client().fget_object(self.bucket, object_key, str(target))
        return target

    def upload_file(self, object_key: str, source_path: str | Path, *, content_type: str = "application/octet-stream"):
        source = Path(source_path)
        self._get_client().fput_object(self.bucket, object_key, str(source), content_type=content_type)
        return object_key

    def upload_bytes(self, object_key: str, content: bytes, *, content_type: str = "application/octet-stream"):
        self._get_client().put_object(
            self.bucket,
            object_key,
            BytesIO(content),
            length=len(content),
            content_type=content_type,
        )
        return object_key
