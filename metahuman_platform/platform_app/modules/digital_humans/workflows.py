from __future__ import annotations

from pathlib import Path

from platform_app.modules.digital_humans.progress import DigitalHumanProgress
from platform_app.modules.digital_humans.repository import (
    DigitalHumanAssetRepository,
    DigitalHumanGenerationTaskRepository,
)
from platform_app.modules.digital_humans.storage import DigitalHumanStorage


class DigitalHumanWorkflowRunner:
    def __init__(
        self,
        *,
        db_path: Path,
        storage: DigitalHumanStorage | None = None,
        progress: DigitalHumanProgress | None = None,
    ):
        self.db_path = Path(db_path)
        self.task_repository = DigitalHumanGenerationTaskRepository(self.db_path)
        self.asset_repository = DigitalHumanAssetRepository(self.db_path)
        self.storage = storage or DigitalHumanStorage()
        self.progress = progress or DigitalHumanProgress()

    def run_generation_task(self, task_id: str):
        task = self.task_repository.get(task_id)
        if task is None:
            raise ValueError("数字人生成任务不存在")
        try:
            self.task_repository.update_status(task_id, status="running")
            self.progress.set(task_id, progress=5, stage="downloading", message="正在下载素材")
            input_paths = self.storage.download_inputs(
                task_id=task_id,
                input_keys=task.get("input_asset_keys_json") or {},
            )

            self.progress.set(task_id, progress=45, stage="generating", message="正在生成视频")
            result_path = self._generate_with_current_backend(task=task, input_paths=input_paths)

            self.progress.set(task_id, progress=85, stage="postprocessing", message="正在上传结果")
            result_key = self.storage.upload_result(
                digital_human_id=task["digital_human_id"],
                task_id=task_id,
                source_path=result_path,
            )
            result_asset = self._register_result_asset(task=task, result_key=result_key)
            updated = self.task_repository.set_result(
                task_id,
                result_key=result_key,
                result_asset_ids=[result_asset["id"]] if result_asset else [],
            )
            self.progress.set(task_id, progress=100, stage="completed", message="已完成")
            return updated
        except Exception as exc:
            self.task_repository.update_status(task_id, status="failed", error_message=str(exc))
            try:
                self.progress.set(task_id, progress=100, stage="failed", message=str(exc))
            except Exception:
                pass
            raise

    def _generate_with_current_backend(self, *, task: dict, input_paths: dict[str, Path]) -> Path:
        # MVP 阶段先复用输入视频作为结果；未来在这里替换成 ComfyUI/换装/换背景生成器。
        return self.storage.make_mock_result(task_id=task["id"], input_paths=input_paths)

    def _register_result_asset(self, *, task: dict, result_key: str):
        existing = self.asset_repository.get_by_storage_key(result_key)
        if existing is not None:
            return existing
        return self.asset_repository.create(
            digital_human_id=task["digital_human_id"],
            asset_type=f"{task['task_type']}_result",
            filename=Path(result_key).name,
            file_path=f"minio://{self.storage.settings.minio_bucket}/{result_key}",
            content_type="video/mp4",
            storage_backend="minio",
            storage_key=result_key,
            metadata={
                "source": "generation_task_result",
                "task_id": task["id"],
                "task_type": task["task_type"],
            },
        )
