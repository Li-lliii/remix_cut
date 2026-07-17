from __future__ import annotations

from pathlib import Path

from platform_app.modules.ai_transforms.repository import (
    AiTransformTaskItemRepository,
    AiTransformTaskRepository,
)
from platform_app.modules.ai_transforms.schemas import SUPPORTED_OPERATIONS
from platform_app.modules.ai_transforms.storage import AiTransformStorage
from platform_app.repositories.role_repository import RoleRepository
from platform_app.repositories.video_repository import VideoRepository


OPERATION_WORKFLOWS = {
    "replace_background": "ai_transform_replace_background",
}


class AiTransformService:
    def __init__(self, *, db_path: Path, storage: AiTransformStorage | None = None):
        self.db_path = Path(db_path)
        self.task_repository = AiTransformTaskRepository(self.db_path)
        self.item_repository = AiTransformTaskItemRepository(self.db_path)
        self.role_repository = RoleRepository(self.db_path)
        self.video_repository = VideoRepository(self.db_path)
        self.storage = storage or AiTransformStorage()

    def create_task(
        self,
        *,
        role_id: str,
        source_video_id: str,
        operations: list[str],
        input_asset_keys: dict[str, str],
        params: dict | None = None,
    ):
        normalized_operations = [str(operation).strip() for operation in operations if str(operation).strip()]
        if not normalized_operations:
            raise ValueError("至少选择一个 AI 变身能力")
        unsupported = [operation for operation in normalized_operations if operation not in SUPPORTED_OPERATIONS]
        if unsupported:
            raise ValueError(f"暂不支持的 AI 变身能力: {', '.join(unsupported)}")
        if self.role_repository.get(role_id) is None:
            raise ValueError("角色不存在")
        video = self.video_repository.get(source_video_id)
        if video is None or video["role_id"] != role_id:
            raise ValueError("原始视频不存在")

        required_fields = ["source_video"]
        if "replace_background" in normalized_operations:
            required_fields.append("background_image")
        self.storage.assert_inputs_exist(input_asset_keys, required_fields)

        task = self.task_repository.create(
            role_id=role_id,
            source_video_id=source_video_id,
            operations=normalized_operations,
            input_asset_keys=input_asset_keys,
            params=params or {},
            status="pending",
        )
        for operation in normalized_operations:
            self.item_repository.create(
                task_id=task["id"],
                operation=operation,
                workflow_name=OPERATION_WORKFLOWS[operation],
                input_params=params or {},
            )
        return self.get_task_detail(task["id"])

    def submit_task(self, task_id: str):
        task = self.task_repository.get(task_id)
        if task is None:
            raise ValueError("AI变身任务不存在")
        if task["status"] not in {"pending", "failed"}:
            raise ValueError(f"当前任务状态不允许提交: {task['status']}")
        self.storage.assert_inputs_exist(
            task.get("input_asset_keys_json") or {},
            self._required_fields_for_task(task),
        )
        task = self.task_repository.update_status(task_id, status="queued")
        try:
            from platform_app.modules.ai_transforms.tasks import run_ai_transform_task

            run_ai_transform_task.delay(task_id)
        except RuntimeError as exc:
            task = self.task_repository.update_status(task_id, status="queued", error_message=str(exc))
        return task

    def get_task_detail(self, task_id: str):
        task = self.task_repository.get(task_id)
        if task is None:
            raise ValueError("AI变身任务不存在")
        result_download_url = ""
        if task.get("output_key"):
            try:
                result_download_url = self.storage.result_download_url(task["output_key"])
            except Exception:
                result_download_url = ""
        return {
            "task": task,
            "items": self.item_repository.list_by_task(task_id),
            "result_download_url": result_download_url,
        }

    def list_tasks(self, *, role_id: str | None = None):
        return {"items": self.task_repository.list(role_id=role_id)}

    def cancel_task(self, task_id: str):
        task = self.task_repository.get(task_id)
        if task is None:
            raise ValueError("AI变身任务不存在")
        if task["status"] in {"success", "failed", "cancelled"}:
            return task
        for item in self.item_repository.list_by_task(task_id):
            if item["status"] not in {"success", "failed", "cancelled"}:
                self.item_repository.update_status(item["id"], status="cancelled")
        return self.task_repository.update_status(task_id, status="cancelled")

    def delete_task(self, task_id: str, *, role_id: str):
        task = self.task_repository.get(task_id)
        if task is None or task["role_id"] != role_id:
            raise ValueError("AI变身任务不存在")
        return self.task_repository.soft_delete(task_id)

    def _required_fields_for_task(self, task: dict) -> list[str]:
        fields = ["source_video"]
        if "replace_background" in (task.get("operations_json") or []):
            fields.append("background_image")
        return fields
