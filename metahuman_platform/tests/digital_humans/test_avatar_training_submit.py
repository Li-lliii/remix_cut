from platform_app.db import init_db
from platform_app.modules.digital_humans.service import DigitalHumanService


class FakeComfyAdapter:
    def __init__(self):
        self.calls = []

    def submit_avatar_training(self, *, task: dict, assets: list[dict]):
        self.calls.append({"task": task, "assets": assets})
        assert task["task_type"] == "material_avatar_build"
        assert any(asset["asset_type"] == "talking_video" for asset in assets)
        return {"backend_job_id": "prompt-123", "raw": {"prompt_id": "prompt-123"}}


class FakeStorage:
    def __init__(self, tmp_path):
        from types import SimpleNamespace

        self.settings = SimpleNamespace(minio_bucket="bs-media")
        self.tmp_path = tmp_path
        self.objects = {}

    def upload_asset_bytes(self, *, digital_human_id: str, asset_type: str, filename: str, content: bytes, content_type: str):
        del content_type
        key = f"digital-humans/{digital_human_id}/assets/{asset_type}-{filename}"
        self.objects[key] = content
        return key

    def result_download_url(self, result_key: str) -> str:
        return f"https://minio.test/{result_key}"

    def download_asset(self, *, storage_key: str, target_path):
        target_path.parent.mkdir(parents=True, exist_ok=True)
        target_path.write_bytes(self.objects[storage_key])
        return target_path


def test_material_avatar_build_task_can_be_submitted_to_comfyui(tmp_path):
    db_path = tmp_path / "app.db"
    init_db(db_path)
    service = DigitalHumanService(db_path=db_path, uploads_dir=tmp_path / "uploads")
    service.storage = FakeStorage(tmp_path)
    service.comfy_adapter = FakeComfyAdapter()

    created = service.create_avatar_training_task(
        name="测试数字人",
        avatar_type="real",
        gender="",
        department="测试部门",
        organization="",
        speaker_name="",
        tags="",
        style="",
        description="",
        talking_video=("input_shot.mp4", b"fake-video", "video/mp4"),
    )

    submitted = service.submit_avatar_training_to_comfyui(created["generation_task"]["id"])

    assert submitted["task"]["status"] == "submitted"
    assert submitted["task"]["backend_job_id"] == "prompt-123"
    assert submitted["comfyui"]["backend_job_id"] == "prompt-123"
    assert len(service.comfy_adapter.calls) == 1


def test_create_from_materials_stores_assets_in_minio_metadata(tmp_path):
    db_path = tmp_path / "app.db"
    init_db(db_path)
    service = DigitalHumanService(db_path=db_path, uploads_dir=tmp_path / "uploads")
    service.storage = FakeStorage(tmp_path)

    created = service.create_avatar_training_task(
        name="测试数字人",
        avatar_type="real",
        gender="",
        department="测试部门",
        organization="",
        speaker_name="",
        tags="",
        style="",
        description="",
        talking_video=("input_shot.mp4", b"fake-video", "video/mp4"),
    )

    asset = created["assets"][0]
    assert asset["asset_type"] == "talking_video"
    assert asset["storage_backend"] == "minio"
    assert asset["storage_key"].startswith(f"digital-humans/{created['digital_human']['id']}/assets/")
    assert asset["file_path"] == f"minio://bs-media/{asset['storage_key']}"
    assert service.storage.objects[asset["storage_key"]] == b"fake-video"
