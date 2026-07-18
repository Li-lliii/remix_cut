from types import SimpleNamespace

import pytest

from conftest import app_client


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

    def download_asset(self, *, storage_key: str, target_path):
        target_path.parent.mkdir(parents=True, exist_ok=True)
        target_path.write_bytes(self.objects.get(storage_key, b"fake-video"))
        return target_path


class FakeMaterialStorage:
    objects = {}

    def __init__(self, *args, **kwargs):
        del args, kwargs

    def upload_file(self, object_key, source_path, *, content_type="application/octet-stream"):
        del content_type
        self.objects[object_key] = source_path.read_bytes()
        return object_key

    def presigned_get_url(self, object_key):
        return f"https://minio.test/{object_key}"

    def download_file(self, object_key, target_path):
        target_path.parent.mkdir(parents=True, exist_ok=True)
        target_path.write_bytes(self.objects[object_key])
        return target_path


class FakeComfyAdapter:
    def __init__(self, *args, **kwargs):
        del args, kwargs

    def submit_avatar_training(self, *, task: dict, assets: list[dict]):
        assert task["task_type"] == "material_avatar_build"
        assert any(asset["asset_type"] == "talking_video" for asset in assets)
        return {"backend_job_id": "prompt-api-123", "raw": {"prompt_id": "prompt-api-123"}}


@pytest.mark.anyio
async def test_create_from_materials_api_stores_metadata_and_minio_asset(tmp_path, monkeypatch):
    db_path = tmp_path / "app.db"
    monkeypatch.setenv("BS_MEDIA_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("BS_MEDIA_DATABASE_URL", f"sqlite:///{db_path}")
    monkeypatch.setenv("BS_MEDIA_UPLOADS_DIR", str(tmp_path / "uploads"))
    monkeypatch.setenv("BS_MEDIA_PLATFORM_LOG_FILE", str(tmp_path / "platform.log"))
    monkeypatch.setattr("platform_app.modules.digital_humans.service.DigitalHumanStorage", FakeStorage)
    monkeypatch.setattr("platform_app.modules.digital_humans.service.DigitalHumanComfyAdapter", FakeComfyAdapter)

    async with app_client() as client:
        response = await client.post(
            "/api/digital-humans/create-from-materials",
            data={
                "name": "测试数字人",
                "avatar_type": "real",
                "department": "测试部门",
            },
            files={"talking_video": ("input_shot.mp4", b"fake-video", "video/mp4")},
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["digital_human"]["name"] == "测试数字人"
    assert payload["profile"]["department"] == "测试部门"
    assert payload["generation_task"]["task_type"] == "material_avatar_build"

    asset = payload["assets"][0]
    assert asset["asset_type"] == "talking_video"
    assert asset["storage_backend"] == "minio"
    assert asset["storage_key"].startswith(f"digital-humans/{payload['digital_human']['id']}/assets/")
    assert asset["file_path"] == f"minio://bs-media/{asset['storage_key']}"


@pytest.mark.anyio
async def test_create_from_materials_accepts_platform_material_ids(tmp_path, monkeypatch):
    db_path = tmp_path / "app.db"
    monkeypatch.setenv("BS_MEDIA_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("BS_MEDIA_DATABASE_URL", f"sqlite:///{db_path}")
    monkeypatch.setenv("BS_MEDIA_UPLOADS_DIR", str(tmp_path / "uploads"))
    monkeypatch.setenv("BS_MEDIA_PLATFORM_LOG_FILE", str(tmp_path / "platform.log"))
    monkeypatch.setenv("BS_MEDIA_DEFAULT_ASR_MODE", "mock")
    monkeypatch.setattr("platform_app.modules.digital_humans.service.DigitalHumanStorage", FakeStorage)
    monkeypatch.setattr("platform_app.modules.digital_humans.service.DigitalHumanComfyAdapter", FakeComfyAdapter)
    monkeypatch.setattr("platform_app.modules.materials.service.MinioObjectStorage", FakeMaterialStorage)

    async with app_client() as client:
        video = await client.post(
            "/api/materials/digital-human/videos/upload",
            files={"video": ("talk.mp4", b"material-video", "video/mp4")},
        )
        image = await client.post(
            "/api/materials/digital-human/images/upload",
            files={"image": ("person.png", b"material-image", "image/png")},
        )
        audio = await client.post(
            "/api/materials/digital-human/audios/upload",
            files={"audio": ("voice.mp3", b"material-audio", "audio/mpeg")},
        )
        response = await client.post(
            "/api/digital-humans/create-from-materials",
            data={
                "name": "平台素材数字人",
                "avatar_type": "real",
                "department": "素材部门",
                "talking_video_material_id": video.json()["id"],
                "person_image_material_id": image.json()["id"],
                "voice_sample_material_id": audio.json()["id"],
            },
        )

    assert response.status_code == 200
    payload = response.json()
    assets = {asset["asset_type"]: asset for asset in payload["assets"]}
    assert set(assets) == {"talking_video", "person_image", "voice_sample"}
    assert assets["talking_video"]["storage_key"] == video.json()["storage_key"]
    assert assets["person_image"]["storage_key"] == image.json()["storage_key"]
    assert assets["voice_sample"]["storage_key"] == audio.json()["storage_key"]
    assert assets["talking_video"]["metadata_json"]["source"] == "material_library"
    assert assets["talking_video"]["metadata_json"]["source_material_asset_id"] == video.json()["id"]
    assert payload["primary_asset"]["id"] == assets["person_image"]["id"]


@pytest.mark.anyio
async def test_submit_comfyui_api_records_backend_job_id(tmp_path, monkeypatch):
    db_path = tmp_path / "app.db"
    monkeypatch.setenv("BS_MEDIA_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("BS_MEDIA_DATABASE_URL", f"sqlite:///{db_path}")
    monkeypatch.setenv("BS_MEDIA_UPLOADS_DIR", str(tmp_path / "uploads"))
    monkeypatch.setenv("BS_MEDIA_PLATFORM_LOG_FILE", str(tmp_path / "platform.log"))
    monkeypatch.setattr("platform_app.modules.digital_humans.service.DigitalHumanStorage", FakeStorage)
    monkeypatch.setattr("platform_app.modules.digital_humans.service.DigitalHumanComfyAdapter", FakeComfyAdapter)

    async with app_client() as client:
        created = await client.post(
            "/api/digital-humans/create-from-materials",
            data={
                "name": "测试数字人",
                "avatar_type": "real",
                "department": "测试部门",
            },
            files={"talking_video": ("input_shot.mp4", b"fake-video", "video/mp4")},
        )
        task_id = created.json()["generation_task"]["id"]

        submitted = await client.post(f"/api/digital-humans/generation-tasks/{task_id}/submit-comfyui")

    assert submitted.status_code == 200
    payload = submitted.json()
    assert payload["task"]["status"] == "submitted"
    assert payload["task"]["backend_job_id"] == "prompt-api-123"
    assert payload["comfyui"]["backend_job_id"] == "prompt-api-123"
