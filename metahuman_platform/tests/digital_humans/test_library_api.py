from types import SimpleNamespace

import pytest

from conftest import app_client
from platform_app.modules.digital_humans.service import DigitalHumanService


class FakeStorage:
    def __init__(self, *args, **kwargs):
        del args, kwargs
        self.settings = SimpleNamespace(minio_bucket="bs-media")
        self.objects = {}

    def upload_asset_bytes(
        self,
        *,
        digital_human_id: str,
        asset_type: str,
        filename: str,
        content: bytes,
        content_type: str,
    ):
        del content_type
        key = f"digital-humans/{digital_human_id}/assets/{asset_type}-{filename}"
        self.objects[key] = content
        return key

    def result_download_url(self, result_key: str) -> str:
        return f"https://minio.test/{result_key}"


def _create_avatar(service: DigitalHumanService, *, name: str, avatar_type: str, department: str):
    return service.create_avatar_training_task(
        name=name,
        avatar_type=avatar_type,
        gender="",
        department=department,
        organization="测试医院",
        speaker_name=name,
        tags="医生,健康",
        style="",
        description=f"{department}{name}",
        talking_video=("input_shot.mp4", b"fake-video", "video/mp4"),
    )


@pytest.mark.anyio
async def test_library_api_supports_search_type_and_status_filters(tmp_path, monkeypatch):
    db_path = tmp_path / "app.db"
    monkeypatch.setenv("BS_MEDIA_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("BS_MEDIA_DATABASE_URL", f"sqlite:///{db_path}")
    monkeypatch.setenv("BS_MEDIA_UPLOADS_DIR", str(tmp_path / "uploads"))
    monkeypatch.setenv("BS_MEDIA_PLATFORM_LOG_FILE", str(tmp_path / "platform.log"))
    monkeypatch.setattr("platform_app.modules.digital_humans.service.DigitalHumanStorage", FakeStorage)

    service = DigitalHumanService(db_path=db_path, uploads_dir=tmp_path / "uploads")
    service.storage = FakeStorage()
    active = _create_avatar(service, name="李医生", avatar_type="real", department="心内科")
    _create_avatar(service, name="王主任", avatar_type="real", department="神经外科")
    _create_avatar(service, name="小云", avatar_type="anime", department="健康科普")
    service.digital_human_repository.update_primary_asset(
        active["digital_human"]["id"],
        active["assets"][0]["id"],
        status="active",
    )

    async with app_client() as client:
        all_response = await client.get("/api/digital-humans")
        filtered_response = await client.get(
            "/api/digital-humans",
            params={"search": "李", "avatar_type": "real", "status": "active"},
        )
        training_response = await client.get("/api/digital-humans", params={"status": "training"})
        type_alias_response = await client.get("/api/digital-humans", params={"type": "anime"})

    assert all_response.status_code == 200
    payload = all_response.json()
    assert payload["total_count"] == 3
    assert payload["filtered_count"] == 3
    assert payload["summary"]["active_count"] == 1
    assert payload["summary"]["training_count"] == 2
    assert set(payload["filters"]["avatar_types"]) == {"anime", "real"}

    filtered = filtered_response.json()
    assert filtered["filtered_count"] == 1
    assert filtered["items"][0]["name"] == "李医生"
    assert filtered["items"][0]["status_group"] == "active"
    assert filtered["items"][0]["status_label"] == "已激活"
    assert filtered["items"][0]["display_asset"]["preview_url"].startswith("https://minio.test/")

    training = training_response.json()
    assert training["filtered_count"] == 2
    assert {item["status_group"] for item in training["items"]} == {"training"}

    type_alias = type_alias_response.json()
    assert type_alias["filtered_count"] == 1
    assert type_alias["items"][0]["avatar_type"] == "anime"
