from pathlib import Path
from types import SimpleNamespace

from platform_app.db import init_db
from platform_app.modules.digital_humans.repository import (
    DigitalHumanAssetRepository,
    DigitalHumanGenerationTaskRepository,
    DigitalHumanRepository,
)
from platform_app.modules.digital_humans.service import DigitalHumanService
from platform_app.modules.digital_humans.storage import UploadObjectSpec
from platform_app.modules.digital_humans.workflows import DigitalHumanWorkflowRunner


class FakeDigitalHumanStorage:
    def __init__(self):
        self.settings = SimpleNamespace(minio_bucket="bs-media")
        self.uploaded_keys = set()

    def create_presigned_uploads(self, *, digital_human_id: str, task_id: str, files: list[UploadObjectSpec]):
        input_keys = {}
        uploads = []
        for file_spec in files:
            object_key = f"digital-humans/{digital_human_id}/tasks/{task_id}/input/{file_spec.filename}"
            input_keys[file_spec.field] = object_key
            uploads.append(
                {
                    "field": file_spec.field,
                    "object_key": object_key,
                    "upload_url": f"https://minio.test/{object_key}",
                    "content_type": file_spec.content_type,
                }
            )
            self.uploaded_keys.add(object_key)
        return input_keys, uploads

    def assert_objects_uploaded(self, input_keys: dict[str, str]):
        missing = [field for field, key in input_keys.items() if key not in self.uploaded_keys]
        if missing:
            raise ValueError(f"素材尚未上传完成: {', '.join(missing)}")

    def result_download_url(self, result_key: str) -> str:
        return f"https://minio.test/download/{result_key}"


class FakeWorkerStorage(FakeDigitalHumanStorage):
    def __init__(self, tmp_path: Path):
        super().__init__()
        self.tmp_path = tmp_path

    def download_inputs(self, *, task_id: str, input_keys: dict[str, str]):
        del task_id
        paths = {}
        for field in input_keys:
            target = self.tmp_path / f"{field}.mp4"
            target.write_bytes(b"fake-video")
            paths[field] = target
        return paths

    def make_mock_result(self, *, task_id: str, input_paths: dict[str, Path]):
        del input_paths
        target = self.tmp_path / f"{task_id}-result.mp4"
        target.write_bytes(b"fake-result")
        return target

    def upload_result(self, *, digital_human_id: str, task_id: str, source_path: str | Path):
        assert Path(source_path).exists()
        return f"digital-humans/{digital_human_id}/tasks/{task_id}/output/result.mp4"


class FakeProgress:
    def __init__(self):
        self.events = []

    def set(self, task_id: str, *, progress: int, stage: str, message: str = "", extra: dict | None = None):
        payload = {"task_id": task_id, "progress": progress, "stage": stage, "message": message, "extra": extra or {}}
        self.events.append(payload)
        return payload

    def get(self, task_id: str):
        for event in reversed(self.events):
            if event["task_id"] == task_id:
                return event
        return {"progress": 0, "stage": "pending", "message": "", "extra": {}}


def _create_digital_human(db_path: Path):
    return DigitalHumanRepository(db_path).create(
        name="李医生",
        avatar_type="real",
        gender="female",
        status="active",
    )


def test_object_upload_task_registers_minio_inputs_for_library_display(tmp_path):
    db_path = tmp_path / "app.db"
    init_db(db_path)
    digital_human = _create_digital_human(db_path)

    service = DigitalHumanService(db_path=db_path, uploads_dir=tmp_path / "uploads")
    service.storage = FakeDigitalHumanStorage()

    created = service.create_object_upload_task(
        digital_human_id=digital_human["id"],
        task_type="change_background",
        workflow_name="digital_human_change_background",
        prompt_text="换成医院诊室背景",
        files=[
            UploadObjectSpec(field="source_video", filename="source.mp4", content_type="video/mp4"),
            UploadObjectSpec(field="background_image", filename="background.png", content_type="image/png"),
        ],
        params={"resolution": "720p"},
    )

    task = created["task"]
    assert task["status"] == "uploading"
    assert set(task["input_asset_keys_json"]) == {"source_video", "background_image"}
    assert len(created["uploads"]) == 2
    assert created["uploads"][0]["upload_url"].startswith("https://minio.test/")

    queued = service.submit_object_upload_task(task["id"])
    assert queued["status"] == "queued"

    assets = DigitalHumanAssetRepository(db_path).list_by_digital_human(digital_human["id"])
    assert {asset["asset_type"] for asset in assets} == {"source_video", "background_image"}
    assert all(asset["storage_backend"] == "minio" for asset in assets)
    assert all(asset["storage_key"] for asset in assets)

    detail = service.get_digital_human_detail(digital_human["id"])
    assert len(detail["assets"]) == 2
    assert all(asset["preview_url"].startswith("https://minio.test/download/") for asset in detail["assets"])


def test_workflow_registers_minio_result_asset_and_marks_task_success(tmp_path):
    db_path = tmp_path / "app.db"
    init_db(db_path)
    digital_human = _create_digital_human(db_path)
    task_repo = DigitalHumanGenerationTaskRepository(db_path)
    task = task_repo.create(
        digital_human_id=digital_human["id"],
        task_type="change_background",
        status="queued",
        prompt_text="换成医院诊室背景",
        workflow_name="digital_human_change_background",
        input_asset_keys={"source_video": "digital-humans/input/source.mp4"},
        params={"resolution": "720p"},
    )

    progress = FakeProgress()
    runner = DigitalHumanWorkflowRunner(
        db_path=db_path,
        storage=FakeWorkerStorage(tmp_path),
        progress=progress,
    )

    updated = runner.run_generation_task(task["id"])

    assert updated["status"] == "success"
    assert updated["result_key"].endswith("/output/result.mp4")
    assert len(updated["result_asset_ids_json"]) == 1
    assert progress.events[-1]["stage"] == "completed"

    result_asset = DigitalHumanAssetRepository(db_path).get(updated["result_asset_ids_json"][0])
    assert result_asset["asset_type"] == "change_background_result"
    assert result_asset["storage_backend"] == "minio"
    assert result_asset["storage_key"] == updated["result_key"]
    assert result_asset["metadata_json"]["task_id"] == task["id"]

