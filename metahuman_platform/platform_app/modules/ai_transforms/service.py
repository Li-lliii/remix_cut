from __future__ import annotations

from pathlib import Path

from platform_app.modules.ai_transforms.repository import (
    AiTransformTaskItemRepository,
    AiTransformTaskRepository,
)
from platform_app.modules.ai_transforms.schemas import CAPABILITIES, ENABLED_OPERATIONS, SUPPORTED_OPERATIONS
from platform_app.modules.ai_transforms.storage import AiTransformStorage
from platform_app.modules.materials.service import MaterialService
from platform_app.repositories.role_repository import RoleRepository
from platform_app.repositories.video_repository import VideoRepository
from platform_app.settings import get_settings
from platform_app.services.asr_adapter import AsrAdapter
from platform_app.services.background_runner import run_in_background
from platform_app.services.video_service import VideoService


OPERATION_WORKFLOWS = {
    "replace_background": "ai_transform_replace_background",
    "replace_speech": "ai_transform_replace_speech",
}

OPERATION_REQUIRED_INPUTS = {
    item["operation"]: ["source_video", *item["required_inputs"]]
    for item in CAPABILITIES
}


class AiTransformService:
    def __init__(
        self,
        *,
        db_path: Path,
        storage: AiTransformStorage | None = None,
        material_service: MaterialService | None = None,
    ):
        self.db_path = Path(db_path)
        self.task_repository = AiTransformTaskRepository(self.db_path)
        self.item_repository = AiTransformTaskItemRepository(self.db_path)
        self.role_repository = RoleRepository(self.db_path)
        self.video_repository = VideoRepository(self.db_path)
        self.storage = storage or AiTransformStorage()
        self.material_service = material_service

    def list_capabilities(self):
        return {"items": CAPABILITIES}

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
        disabled = [operation for operation in normalized_operations if operation not in ENABLED_OPERATIONS]
        if disabled:
            raise ValueError(f"能力尚未接入工作流: {', '.join(disabled)}")
        self._validate_operation_params(normalized_operations, params or {})
        if self.role_repository.get(role_id) is None:
            raise ValueError("角色不存在")
        video = self.video_repository.get(source_video_id)
        if video is None or video["role_id"] != role_id:
            raise ValueError("原始视频不存在")

        required_fields = self._required_fields_for_operations(normalized_operations)
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

    def upload_and_run(
        self,
        *,
        role_id: str,
        source_video_id: str,
        operations: list[str],
        background_image_filename: str | None = None,
        background_image_content: bytes | None = None,
        owner_user_id: str = "",
        params: dict | None = None,
    ):
        normalized_operations = self._normalize_operations(operations)
        if "replace_background" in normalized_operations and not background_image_content:
            raise ValueError("换背景需要上传 background_image")
        self._validate_operation_params(normalized_operations, params or {})

        input_asset_keys = {
            "source_video": self._source_video_storage_key(
                role_id=role_id,
                source_video_id=source_video_id,
            )
        }
        if "replace_background" in normalized_operations:
            material = self._get_material_service().save_background_image(
                filename=background_image_filename or "background.png",
                content=background_image_content or b"",
                owner_user_id=owner_user_id,
                visibility="private",
                title=background_image_filename or "background.png",
                tags=["ai_transform"],
                metadata={
                    "source": "ai_transform_upload_and_run",
                    "role_id": role_id,
                    "source_video_id": source_video_id,
                },
            )
            input_asset_keys["background_image"] = material["storage_key"]

        detail = self.create_task(
            role_id=role_id,
            source_video_id=source_video_id,
            operations=normalized_operations,
            input_asset_keys=input_asset_keys,
            params=params or {},
        )
        queued = self.submit_task(detail["task"]["id"])
        detail = self.get_task_detail(detail["task"]["id"])
        return {
            **detail,
            "task_id": detail["task"]["id"],
            "status": queued["status"],
            "detail_url": f"/api/ai-transforms/tasks/{detail['task']['id']}",
        }

    def upload_source_video(
        self,
        *,
        role_id: str,
        filename: str,
        content: bytes,
    ):
        if not content:
            raise ValueError("原视频文件为空")
        if self.role_repository.get(role_id) is None:
            raise ValueError("角色不存在")

        video_service = self._build_video_service()
        video = video_service.save_upload(
            role_id=role_id,
            filename=filename or "source.mp4",
            content=content,
        )
        run_in_background(video_service.process_video_asr, video["id"])
        return {
            "source_video": video,
            "source_video_id": video["id"],
            "asr_status_url": f"/api/videos/{video['id']}/asr",
            "capabilities_url": "/api/ai-transforms/capabilities",
            "capabilities": CAPABILITIES,
        }

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
        return self._required_fields_for_operations(task.get("operations_json") or [])

    def _required_fields_for_operations(self, operations: list[str]) -> list[str]:
        fields: list[str] = []
        for operation in operations:
            for field in OPERATION_REQUIRED_INPUTS.get(operation, ["source_video"]):
                if field not in fields:
                    fields.append(field)
        return fields or ["source_video"]

    def _normalize_operations(self, operations: list[str]) -> list[str]:
        normalized_operations = [str(operation).strip() for operation in operations if str(operation).strip()]
        if not normalized_operations:
            raise ValueError("至少选择一个 AI 变身能力")
        unsupported = [operation for operation in normalized_operations if operation not in SUPPORTED_OPERATIONS]
        if unsupported:
            raise ValueError(f"暂不支持的 AI 变身能力: {', '.join(unsupported)}")
        disabled = [operation for operation in normalized_operations if operation not in ENABLED_OPERATIONS]
        if disabled:
            raise ValueError(f"能力尚未接入工作流: {', '.join(disabled)}")
        return normalized_operations

    def _validate_operation_params(self, operations: list[str], params: dict):
        if "replace_speech" in operations and not str(params.get("speech_text") or "").strip():
            raise ValueError("换口播需要传 speech_text")

    def _source_video_storage_key(self, *, role_id: str, source_video_id: str) -> str:
        if self.role_repository.get(role_id) is None:
            raise ValueError("角色不存在")
        video = self.video_repository.get(source_video_id)
        if video is None or video["role_id"] != role_id:
            raise ValueError("原始视频不存在")
        material_asset_id = str(video.get("material_asset_id") or "").strip()
        if not material_asset_id:
            raise ValueError("原始视频未关联 MinIO 素材")
        asset = self._get_material_service().get_asset(material_asset_id)
        if asset.get("storage_backend") != "minio" or not asset.get("storage_key"):
            raise ValueError("原始视频不是 MinIO 素材")
        return asset["storage_key"]

    def _get_material_service(self) -> MaterialService:
        if self.material_service is not None:
            return self.material_service
        from platform_app.settings import get_settings

        settings = get_settings()
        self.material_service = MaterialService(db_path=self.db_path, uploads_dir=settings.uploads_dir)
        return self.material_service

    def _build_video_service(self) -> VideoService:
        settings = get_settings()
        return VideoService(
            db_path=self.db_path,
            uploads_dir=settings.uploads_dir,
            asr_adapter=AsrAdapter(
                settings.asr_mode,
                service_base_url=settings.asr_service_base_url,
                connect_timeout_sec=settings.algo_connect_timeout_sec,
                read_timeout_sec=settings.algo_read_timeout_sec,
            ),
        )
