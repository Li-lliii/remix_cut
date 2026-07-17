from __future__ import annotations

import pytest

from conftest import app_client


class FakeAiTransformStorage:
    existing_keys = {"videos/source.mp4", "backgrounds/bg.png"}

    def __init__(self, *args, **kwargs):
        del args, kwargs

    def assert_inputs_exist(self, input_asset_keys: dict[str, str], required_fields: list[str]):
        missing = [
            field
            for field in required_fields
            if input_asset_keys.get(field) not in self.existing_keys
        ]
        if missing:
            raise ValueError(f"素材不存在或尚未上传: {', '.join(missing)}")

    def result_download_url(self, result_key: str) -> str:
        return f"https://minio.test/{result_key}"


class FakeMinioObjectStorage:
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


async def _create_role_and_video(client):
    role = (
        await client.post(
            "/api/roles",
            json={"name": "AI变身角色", "description": "", "tags": ["测试"]},
        )
    ).json()
    video = (
        await client.post(
            f"/api/roles/{role['id']}/videos/upload",
            files={"video": ("source.mp4", b"fake-video", "video/mp4")},
        )
    ).json()
    return role, video


@pytest.mark.anyio
async def test_create_ai_transform_background_task(tmp_path, monkeypatch):
    monkeypatch.setenv("BS_MEDIA_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("BS_MEDIA_UPLOADS_DIR", str(tmp_path / "uploads"))
    monkeypatch.setenv("BS_MEDIA_DEFAULT_ASR_MODE", "mock")
    monkeypatch.setattr("platform_app.modules.materials.service.MinioObjectStorage", FakeMinioObjectStorage)
    monkeypatch.setattr("platform_app.modules.ai_transforms.service.AiTransformStorage", FakeAiTransformStorage)
    monkeypatch.setattr("platform_app.modules.ai_transforms.api.AiTransformStorage", FakeAiTransformStorage, raising=False)

    async with app_client() as client:
        role, video = await _create_role_and_video(client)
        response = await client.post(
            "/api/ai-transforms/tasks",
            json={
                "role_id": role["id"],
                "source_video_id": video["id"],
                "operations": ["replace_background"],
                "input_asset_keys": {
                    "source_video": "videos/source.mp4",
                    "background_image": "backgrounds/bg.png",
                },
                "params": {"background_mode": "image"},
            },
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["task"]["status"] == "pending"
    assert payload["task"]["operations_json"] == ["replace_background"]
    assert payload["items"][0]["operation"] == "replace_background"
    assert payload["items"][0]["workflow_name"] == "ai_transform_replace_background"


@pytest.mark.anyio
async def test_ai_transform_rejects_unsupported_operation(tmp_path, monkeypatch):
    monkeypatch.setenv("BS_MEDIA_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("BS_MEDIA_UPLOADS_DIR", str(tmp_path / "uploads"))
    monkeypatch.setenv("BS_MEDIA_DEFAULT_ASR_MODE", "mock")
    monkeypatch.setattr("platform_app.modules.materials.service.MinioObjectStorage", FakeMinioObjectStorage)
    monkeypatch.setattr("platform_app.modules.ai_transforms.service.AiTransformStorage", FakeAiTransformStorage)

    async with app_client() as client:
        role, video = await _create_role_and_video(client)
        response = await client.post(
            "/api/ai-transforms/tasks",
            json={
                "role_id": role["id"],
                "source_video_id": video["id"],
                "operations": ["replace_background", "replace_clothes"],
                "input_asset_keys": {
                    "source_video": "videos/source.mp4",
                    "background_image": "backgrounds/bg.png",
                },
            },
        )

    assert response.status_code == 400
    assert "replace_clothes" in response.json()["error"]["message"]


@pytest.mark.anyio
async def test_submit_ai_transform_task_queues_celery(tmp_path, monkeypatch):
    monkeypatch.setenv("BS_MEDIA_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("BS_MEDIA_UPLOADS_DIR", str(tmp_path / "uploads"))
    monkeypatch.setenv("BS_MEDIA_DEFAULT_ASR_MODE", "mock")
    monkeypatch.setattr("platform_app.modules.materials.service.MinioObjectStorage", FakeMinioObjectStorage)
    monkeypatch.setattr("platform_app.modules.ai_transforms.service.AiTransformStorage", FakeAiTransformStorage)

    queued = []

    def fake_delay(task_id: str):
        queued.append(task_id)

    monkeypatch.setattr("platform_app.modules.ai_transforms.tasks.run_ai_transform_task.delay", fake_delay)

    async with app_client() as client:
        role, video = await _create_role_and_video(client)
        created = await client.post(
            "/api/ai-transforms/tasks",
            json={
                "role_id": role["id"],
                "source_video_id": video["id"],
                "operations": ["replace_background"],
                "input_asset_keys": {
                    "source_video": "videos/source.mp4",
                    "background_image": "backgrounds/bg.png",
                },
            },
        )
        task_id = created.json()["task"]["id"]

        response = await client.post("/api/ai-transforms/tasks/submit", json={"task_id": task_id})

    assert response.status_code == 200
    assert response.json()["status"] == "queued"
    assert queued == [task_id]


def test_replace_background_workflow_defaults_patch_real_comfyui_workflow():
    from scripts.run_comfyui_workflow import prepare_workflow
    from platform_app.modules.ai_transforms.comfy_adapter import DEFAULT_REPLACE_BACKGROUND_OVERRIDES

    prompt = prepare_workflow(
        workflow_path="workstream/ai_transforms/replace_background_api.json",
        video_filename="video-input.mp4",
        background_filename="bg-input.png",
        output_prefix="ai_transforms/task-1/result",
        params={"node_overrides": DEFAULT_REPLACE_BACKGROUND_OVERRIDES},
    )

    assert prompt["178"]["class_type"] == "VHS_LoadVideo"
    assert prompt["178"]["inputs"]["video"] == "video-input.mp4"
    assert prompt["225"]["class_type"] == "LoadImage"
    assert prompt["225"]["inputs"]["image"] == "bg-input.png"
    assert prompt["176"]["class_type"] == "VHS_VideoCombine"
    assert prompt["176"]["inputs"]["filename_prefix"] == "ai_transforms/task-1/result"
    assert prompt["176"]["inputs"]["save_output"] is True
