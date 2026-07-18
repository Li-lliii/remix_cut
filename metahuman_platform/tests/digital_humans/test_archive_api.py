from types import SimpleNamespace

import pytest

from conftest import app_client
from platform_app.modules.digital_humans.repository import (
    DigitalHumanAssetRepository,
    DigitalHumanProfileRepository,
    DigitalHumanRepository,
)


class FakeArchiveStorage:
    def __init__(self, *args, **kwargs):
        del args, kwargs
        self.settings = SimpleNamespace(minio_bucket="bs-media")
        self.objects = {}

    def upload_archive_asset_bytes(
        self,
        *,
        digital_human_id: str,
        asset_type: str,
        upload_id: str,
        filename: str,
        content: bytes,
        content_type: str,
    ):
        del content_type
        key = f"digital-humans/{digital_human_id}/archive/{asset_type}/{upload_id}/{filename}"
        self.objects[key] = content
        return key

    def result_download_url(self, result_key: str) -> str:
        return f"https://minio.test/{result_key}"


def seed_digital_human(db_path):
    digital_human = DigitalHumanRepository(db_path).create(
        name="李医生",
        avatar_type="real",
        gender="female",
        status="active",
    )
    profile = DigitalHumanProfileRepository(db_path).create(
        digital_human_id=digital_human["id"],
        department="心内科",
        organization="测试医院",
        speaker_name="李医生",
        tags=["医生", "口播"],
        style="真人",
        description="测试数字人档案",
    )
    return digital_human, profile


def seed_creation_assets(db_path, digital_human_id: str):
    repository = DigitalHumanAssetRepository(db_path)
    return [
        repository.create(
            digital_human_id=digital_human_id,
            asset_type="talking_video",
            filename="talking.mp4",
            file_path=f"minio://bs-media/digital-humans/{digital_human_id}/assets/talking_video.mp4",
            content_type="video/mp4",
            storage_backend="minio",
            storage_key=f"digital-humans/{digital_human_id}/assets/talking_video.mp4",
            metadata={"source": "create_from_materials"},
        ),
        repository.create(
            digital_human_id=digital_human_id,
            asset_type="voice_sample",
            filename="voice.wav",
            file_path=f"minio://bs-media/digital-humans/{digital_human_id}/assets/voice_sample.wav",
            content_type="audio/wav",
            storage_backend="minio",
            storage_key=f"digital-humans/{digital_human_id}/assets/voice_sample.wav",
            metadata={"source": "create_from_materials"},
        ),
        repository.create(
            digital_human_id=digital_human_id,
            asset_type="person_image",
            filename="person.png",
            file_path=f"minio://bs-media/digital-humans/{digital_human_id}/assets/person_image.png",
            content_type="image/png",
            storage_backend="minio",
            storage_key=f"digital-humans/{digital_human_id}/assets/person_image.png",
            metadata={"source": "create_from_materials"},
        ),
    ]


@pytest.mark.anyio
async def test_digital_human_archive_uploads_and_groups_assets(tmp_path, monkeypatch):
    db_path = tmp_path / "app.db"
    monkeypatch.setenv("BS_MEDIA_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("BS_MEDIA_DATABASE_URL", f"sqlite:///{db_path}")
    monkeypatch.setenv("BS_MEDIA_PLATFORM_LOG_FILE", str(tmp_path / "platform.log"))
    monkeypatch.setattr(
        "platform_app.modules.digital_humans.archive_service.DigitalHumanStorage",
        FakeArchiveStorage,
    )
    digital_human, _ = seed_digital_human(db_path)

    async with app_client() as client:
        empty_list = await client.get("/api/digital-human-archive")
        video_response = await client.post(
            f"/api/digital-human-archive/{digital_human['id']}/source-video/upload",
            files={"video": ("source.mp4", b"fake-video", "video/mp4")},
        )
        audio_response = await client.post(
            f"/api/digital-human-archive/{digital_human['id']}/source-audio/upload",
            files={"audio": ("source.wav", b"fake-audio", "audio/wav")},
        )
        image_response = await client.post(
            f"/api/digital-human-archive/{digital_human['id']}/source-image/upload",
            files={"image": ("source.png", b"fake-image", "image/png")},
        )
        detail_response = await client.get(f"/api/digital-human-archive/{digital_human['id']}")
        list_response = await client.get("/api/digital-human-archive")

    assert empty_list.status_code == 200
    assert empty_list.json()["items"][0]["asset_counts"] == {
        "source_video": 0,
        "source_audio": 0,
        "source_image": 0,
    }

    assert video_response.status_code == 200
    assert video_response.json()["asset_type"] == "source_video"
    assert video_response.json()["storage_backend"] == "minio"
    assert "/archive/source_video/" in video_response.json()["storage_key"]

    assert audio_response.status_code == 200
    assert audio_response.json()["asset_type"] == "source_audio"

    assert image_response.status_code == 200
    assert image_response.json()["asset_type"] == "source_image"
    assert image_response.json()["preview_url"].startswith("https://minio.test/")

    detail = detail_response.json()
    assert detail_response.status_code == 200
    assert detail["digital_human"]["id"] == digital_human["id"]
    assert detail["profile"]["department"] == "心内科"
    assert len(detail["assets"]["source_video"]) == 1
    assert len(detail["assets"]["source_audio"]) == 1
    assert len(detail["assets"]["source_image"]) == 1
    assert detail["asset_counts"] == {
        "source_video": 1,
        "source_audio": 1,
        "source_image": 1,
    }

    list_item = list_response.json()["items"][0]
    assert list_response.status_code == 200
    assert list_item["digital_human"]["id"] == digital_human["id"]
    assert list_item["asset_counts"]["source_video"] == 1


@pytest.mark.anyio
async def test_archive_detail_maps_creation_assets_to_source_groups(tmp_path, monkeypatch):
    db_path = tmp_path / "app.db"
    monkeypatch.setenv("BS_MEDIA_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("BS_MEDIA_DATABASE_URL", f"sqlite:///{db_path}")
    monkeypatch.setenv("BS_MEDIA_PLATFORM_LOG_FILE", str(tmp_path / "platform.log"))
    monkeypatch.setattr(
        "platform_app.modules.digital_humans.archive_service.DigitalHumanStorage",
        FakeArchiveStorage,
    )
    digital_human, _ = seed_digital_human(db_path)
    seed_creation_assets(db_path, digital_human["id"])

    async with app_client() as client:
        detail_response = await client.get(f"/api/digital-human-archive/{digital_human['id']}")
        list_response = await client.get("/api/digital-human-archive")

    assert detail_response.status_code == 200
    detail = detail_response.json()
    assert detail["asset_counts"] == {
        "source_video": 1,
        "source_audio": 1,
        "source_image": 1,
    }
    assert detail["assets"]["source_video"][0]["asset_type"] == "talking_video"
    assert detail["assets"]["source_video"][0]["archive_asset_type"] == "source_video"
    assert detail["assets"]["source_audio"][0]["asset_type"] == "voice_sample"
    assert detail["assets"]["source_image"][0]["asset_type"] == "person_image"

    list_item = list_response.json()["items"][0]
    assert list_item["asset_counts"] == {
        "source_video": 1,
        "source_audio": 1,
        "source_image": 1,
    }
