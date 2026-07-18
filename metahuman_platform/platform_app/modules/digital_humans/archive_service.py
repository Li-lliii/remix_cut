from __future__ import annotations

import uuid

from platform_app.modules.digital_humans.repository import (
    DigitalHumanAssetRepository,
    DigitalHumanGenerationTaskRepository,
    DigitalHumanProfileRepository,
    DigitalHumanRepository,
)
from platform_app.modules.digital_humans.storage import DigitalHumanStorage


ARCHIVE_ASSET_TYPES = ("source_video", "source_audio", "source_image")
ARCHIVE_ASSET_TYPE_MAP = {
    "source_video": "source_video",
    "talking_video": "source_video",
    "source_audio": "source_audio",
    "voice_sample": "source_audio",
    "source_image": "source_image",
    "person_image": "source_image",
}


class DigitalHumanArchiveService:
    def __init__(self, *, db_path):
        self.digital_human_repository = DigitalHumanRepository(db_path)
        self.profile_repository = DigitalHumanProfileRepository(db_path)
        self.asset_repository = DigitalHumanAssetRepository(db_path)
        self.task_repository = DigitalHumanGenerationTaskRepository(db_path)
        self.storage = DigitalHumanStorage()

    def list_archives(self):
        items = []
        for digital_human in self.digital_human_repository.list():
            profile = self.profile_repository.get_by_digital_human(digital_human["id"])
            assets = self._archive_assets(digital_human["id"])
            items.append(
                {
                    "digital_human": digital_human,
                    "profile": profile,
                    "asset_counts": self._asset_counts(assets),
                    "latest_asset_at": max(
                        (asset.get("created_at") for asset in assets if asset.get("created_at")),
                        default=None,
                    ),
                }
            )
        return {"items": items, "total_count": len(items)}

    def get_archive_detail(self, digital_human_id: str):
        digital_human = self.digital_human_repository.get(digital_human_id)
        if digital_human is None:
            raise ValueError("数字人不存在")

        grouped_assets = {asset_type: [] for asset_type in ARCHIVE_ASSET_TYPES}
        for asset in self._archive_assets(digital_human_id):
            grouped_assets[self._archive_asset_type(asset)].append(self._enrich_asset(asset))

        return {
            "digital_human": digital_human,
            "profile": self.profile_repository.get_by_digital_human(digital_human_id),
            "assets": grouped_assets,
            "asset_counts": {asset_type: len(items) for asset_type, items in grouped_assets.items()},
            "generation_tasks": self.task_repository.list_by_digital_human(digital_human_id),
        }

    def upload_source_video(self, *, digital_human_id: str, filename: str, content: bytes, content_type: str):
        return self._upload_archive_asset(
            digital_human_id=digital_human_id,
            asset_type="source_video",
            filename=filename,
            content=content,
            content_type=content_type,
        )

    def upload_source_audio(self, *, digital_human_id: str, filename: str, content: bytes, content_type: str):
        return self._upload_archive_asset(
            digital_human_id=digital_human_id,
            asset_type="source_audio",
            filename=filename,
            content=content,
            content_type=content_type,
        )

    def upload_source_image(self, *, digital_human_id: str, filename: str, content: bytes, content_type: str):
        return self._upload_archive_asset(
            digital_human_id=digital_human_id,
            asset_type="source_image",
            filename=filename,
            content=content,
            content_type=content_type,
        )

    def _upload_archive_asset(
        self,
        *,
        digital_human_id: str,
        asset_type: str,
        filename: str,
        content: bytes,
        content_type: str,
    ):
        digital_human = self.digital_human_repository.get(digital_human_id)
        if digital_human is None:
            raise ValueError("数字人不存在")
        if not content:
            raise ValueError("上传文件不能为空")

        upload_id = uuid.uuid4().hex
        storage_key = self.storage.upload_archive_asset_bytes(
            digital_human_id=digital_human_id,
            asset_type=asset_type,
            upload_id=upload_id,
            filename=filename,
            content=content,
            content_type=content_type,
        )
        asset = self.asset_repository.create(
            digital_human_id=digital_human_id,
            asset_type=asset_type,
            filename=filename,
            file_path=f"minio://{self.storage.settings.minio_bucket}/{storage_key}",
            content_type=content_type,
            storage_backend="minio",
            storage_key=storage_key,
            metadata={"source": "digital_human_archive", "upload_id": upload_id},
        )
        return self._enrich_asset(asset)

    def _archive_assets(self, digital_human_id: str):
        return [
            asset
            for asset in self.asset_repository.list_by_digital_human(digital_human_id)
            if asset["asset_type"] in ARCHIVE_ASSET_TYPE_MAP
        ]

    def _asset_counts(self, assets: list[dict]):
        counts = {asset_type: 0 for asset_type in ARCHIVE_ASSET_TYPES}
        for asset in assets:
            counts[self._archive_asset_type(asset)] += 1
        return counts

    def _archive_asset_type(self, asset: dict) -> str:
        return ARCHIVE_ASSET_TYPE_MAP[asset["asset_type"]]

    def _enrich_asset(self, asset: dict):
        preview_url = ""
        if asset.get("storage_backend") == "minio" and asset.get("storage_key"):
            preview_url = self.storage.result_download_url(asset["storage_key"])
        return {
            **asset,
            "archive_asset_type": self._archive_asset_type(asset),
            "preview_url": preview_url,
        }
