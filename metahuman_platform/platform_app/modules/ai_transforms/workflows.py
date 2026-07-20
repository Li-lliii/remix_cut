from __future__ import annotations

import os
import shutil
import time
from pathlib import Path

from platform_app.modules.ai_transforms.comfy_adapter import AiTransformComfyAdapter
from platform_app.modules.ai_transforms.repository import (
    AiTransformTaskItemRepository,
    AiTransformTaskRepository,
)
from platform_app.modules.ai_transforms.storage import AiTransformStorage
from platform_app.settings import get_settings


TERMINAL_STATES = {"success", "failed", "cancelled"}


class AiTransformWorkflowRunner:
    def __init__(
        self,
        *,
        db_path: Path,
        storage: AiTransformStorage | None = None,
        comfy_adapter: AiTransformComfyAdapter | None = None,
    ):
        self.db_path = Path(db_path)
        self.task_repository = AiTransformTaskRepository(self.db_path)
        self.item_repository = AiTransformTaskItemRepository(self.db_path)
        self.storage = storage or AiTransformStorage()
        self.comfy_adapter = comfy_adapter or AiTransformComfyAdapter()

    def run_task(self, task_id: str, *, poll_interval_sec: float = 3.0, timeout_sec: float = 3600.0):
        task = self.task_repository.get(task_id)
        if task is None:
            raise ValueError("AI变身任务不存在")
        if task["status"] in TERMINAL_STATES:
            return task

        try:
            self.task_repository.update_status(task_id, status="running")
            local_inputs = self.storage.download_inputs(
                task_id=task_id,
                input_asset_keys=task.get("input_asset_keys_json") or {},
            )
            items = self.item_repository.list_by_task(task_id)
            current_video = local_inputs.get("source_video")
            if current_video is None:
                raise ValueError("缺少 source_video 输入素材")

            last_operation = "replace_background"
            for item in items:
                last_operation = item["operation"]
                if item["operation"] == "replace_background":
                    current_video = self._run_replace_background(
                        task=task,
                        item=item,
                        current_video=current_video,
                        local_inputs=local_inputs,
                        poll_interval_sec=poll_interval_sec,
                        timeout_sec=timeout_sec,
                    )
                    continue
                if item["operation"] == "replace_speech":
                    current_video = self._run_replace_speech(
                        task=task,
                        item=item,
                        current_video=current_video,
                        poll_interval_sec=poll_interval_sec,
                        timeout_sec=timeout_sec,
                    )
                    continue
                else:
                    raise ValueError(f"暂不支持的 AI 变身能力: {item['operation']}")

            output_key = self.storage.upload_result(task_id=task_id, source_path=current_video, operation=last_operation)
            return self.task_repository.set_output(task_id, output_key=output_key)
        except Exception as exc:
            self.task_repository.update_status(task_id, status="failed", error_message=str(exc))
            raise

    def _run_replace_background(
        self,
        *,
        task: dict,
        item: dict,
        current_video: Path,
        local_inputs: dict[str, Path],
        poll_interval_sec: float,
        timeout_sec: float,
    ) -> Path:
        background = local_inputs.get("background_image")
        if background is None:
            raise ValueError("缺少 background_image 输入素材")

        self.item_repository.update_status(item["id"], status="running")
        output_dir = get_settings().generated_dir / "ai_transforms" / task["id"]
        output_dir.mkdir(parents=True, exist_ok=True)
        try:
            submitted = self.comfy_adapter.submit_replace_background(
                task_id=task["id"],
                source_video_path=current_video,
                background_image_path=background,
                output_dir=output_dir,
                params=task.get("params_json") or {},
            )
        except Exception as exc:
            self.item_repository.update_status(item["id"], status="failed", error_message=str(exc))
            raise
        backend_job_id = submitted["backend_job_id"]
        self.item_repository.update_status(item["id"], status="submitted", backend_job_id=backend_job_id)

        started = time.monotonic()
        while time.monotonic() - started <= timeout_sec:
            try:
                result = self.comfy_adapter.poll(backend_job_id)
            except Exception as exc:
                self.item_repository.update_status(item["id"], status="failed", error_message=str(exc))
                raise
            status = result.get("status")
            if status == "pending":
                time.sleep(poll_interval_sec)
                continue
            if status == "success":
                output_video_url = str(result.get("output_video_url") or "").strip()
                if not output_video_url:
                    raise RuntimeError("ComfyUI 生成成功但未返回 output_video_url")
                output_path = Path(output_video_url).expanduser().resolve()
                if not output_path.exists():
                    raise RuntimeError(f"ComfyUI 输出文件不存在: {output_path}")
                item_output_key = self.storage.upload_result(
                    task_id=task["id"],
                    source_path=output_path,
                    operation=item["operation"],
                )
                self.item_repository.update_status(item["id"], status="success", output_key=item_output_key)
                return output_path
            message = str(result.get("message") or "ComfyUI 生成失败")
            self.item_repository.update_status(item["id"], status="failed", error_message=message)
            raise RuntimeError(message)

        self.item_repository.update_status(item["id"], status="failed", error_message="ComfyUI 生成超时")
        raise TimeoutError("ComfyUI 生成超时")

    def _run_replace_speech(
        self,
        *,
        task: dict,
        item: dict,
        current_video: Path,
        poll_interval_sec: float,
        timeout_sec: float,
    ) -> Path:
        speech_text = str((task.get("params_json") or {}).get("speech_text") or "").strip()
        if not speech_text:
            raise ValueError("缺少 speech_text")

        settings = get_settings()
        os.environ.setdefault("BS_MEDIA_TTS_SERVICE_BASE_URL", settings.tts_service_base_url)
        os.environ.setdefault("BS_MEDIA_COMFY_SERVICE_BASE_URL", settings.comfy_service_base_url)
        os.environ.setdefault("BS_MEDIA_COMFY_MODE", settings.comfy_mode)
        os.environ.setdefault("BS_MEDIA_ALGO_CONNECT_TIMEOUT_SEC", str(settings.algo_connect_timeout_sec))
        os.environ.setdefault("BS_MEDIA_ALGO_READ_TIMEOUT_SEC", str(settings.algo_read_timeout_sec))

        from platform_app.modules.ai_transforms.speech.pipeline import (
            poll_lip_sync_generation_with_output_dir,
            submit_lip_sync_generation,
        )

        self.item_repository.update_status(item["id"], status="running")
        temp_dir = settings.temp_dir / "ai_transforms" / task["id"] / "replace_speech"
        output_dir = settings.generated_dir / "ai_transforms" / task["id"] / "replace_speech"
        temp_dir.mkdir(parents=True, exist_ok=True)
        output_dir.mkdir(parents=True, exist_ok=True)
        try:
            submitted = submit_lip_sync_generation(
                task_id=task["id"],
                base_video_path=str(current_video.expanduser().resolve()),
                script_text=speech_text,
                aspect_mode=str((task.get("params_json") or {}).get("aspect_mode") or "default"),
                resolution=str((task.get("params_json") or {}).get("resolution") or "720p"),
                subtitle_enabled=bool((task.get("params_json") or {}).get("subtitle_enabled", True)),
                temp_dir=str(temp_dir.resolve()),
                output_dir=str(output_dir.resolve()),
            )
        except Exception as exc:
            self.item_repository.update_status(item["id"], status="failed", error_message=str(exc))
            raise

        backend_job_id = str(submitted.get("video_job_id") or "").strip()
        if not backend_job_id:
            raise RuntimeError("换口播未返回有效 video_job_id")
        self.item_repository.update_status(item["id"], status="submitted", backend_job_id=backend_job_id)

        started = time.monotonic()
        while time.monotonic() - started <= timeout_sec:
            try:
                result = poll_lip_sync_generation_with_output_dir(
                    task_id=task["id"],
                    video_job_id=backend_job_id,
                    output_dir=str(output_dir.resolve()),
                )
            except Exception as exc:
                self.item_repository.update_status(item["id"], status="failed", error_message=str(exc))
                raise
            status = result.get("status")
            if status == "pending":
                time.sleep(poll_interval_sec)
                continue
            if status == "success":
                output_path = Path(str(result.get("output_video_url") or "")).expanduser().resolve()
                if not output_path.exists():
                    raise RuntimeError(f"换口播输出文件不存在: {output_path}")
                item_output_key = self.storage.upload_result(
                    task_id=task["id"],
                    source_path=output_path,
                    operation=item["operation"],
                )
                self.item_repository.update_status(item["id"], status="success", output_key=item_output_key)
                return output_path
            message = str(result.get("message") or "换口播生成失败")
            self.item_repository.update_status(item["id"], status="failed", error_message=message)
            raise RuntimeError(message)

        self.item_repository.update_status(item["id"], status="failed", error_message="换口播生成超时")
        raise TimeoutError("换口播生成超时")

    def make_mock_result(self, *, task_id: str, source_path: Path) -> Path:
        output_dir = get_settings().temp_dir / "ai_transforms" / task_id / "output"
        output_dir.mkdir(parents=True, exist_ok=True)
        target = output_dir / "result.mp4"
        shutil.copyfile(source_path, target)
        return target
