import logging
import time
import threading
from datetime import datetime, timezone
from pathlib import Path

from platform_app.repositories.asr_repository import AsrRepository
from platform_app.repositories.lip_sync_repository import (
    LipSyncProjectRepository,
    LipSyncTaskRepository,
    ScriptCandidateRepository,
)
from platform_app.repositories.review_repository import ReviewRecordRepository
from platform_app.repositories.video_repository import VideoRepository
from platform_app.services.background_runner import run_in_background
from platform_app.services.file_cleanup_service import FileCleanupService
from platform_app.services.lip_sync_generation_adapter import LipSyncGenerationAdapter


logger = logging.getLogger(__name__)

LIP_SYNC_HEARTBEAT_LOG_INTERVAL_SEC = 30.0
LIP_SYNC_HEARTBEAT_WARN_AFTER_SEC = 10 * 60.0
LIP_SYNC_ACTIVE_STATUSES = {"starting", "video_generating"}
LIP_SYNC_TERMINAL_STATUSES = {"success", "failed", "cancelled"}
LIP_SYNC_SCHEDULER_LOCK = threading.Lock()


def _elapsed_seconds_since(iso_ts: str | None) -> float | None:
    if not iso_ts:
        return None
    try:
        started = datetime.fromisoformat(str(iso_ts))
    except Exception:
        return None
    now = datetime.now(timezone.utc)
    try:
        return max(0.0, (now - started).total_seconds())
    except Exception:
        return None


def _format_elapsed_message(message: str, elapsed_sec: float | None) -> str:
    if elapsed_sec is None:
        return message
    return f"{message}: elapsed_sec={elapsed_sec:.1f}"


class LipSyncService:
    def __init__(
        self,
        *,
        db_path: Path,
        temp_dir: Path,
        generated_dir: Path,
        generation_adapter=None,
    ):
        self.db_path = Path(db_path)
        self.temp_dir = Path(temp_dir)
        self.generated_dir = Path(generated_dir)
        self.project_repository = LipSyncProjectRepository(self.db_path)
        self.candidate_repository = ScriptCandidateRepository(self.db_path)
        self.task_repository = LipSyncTaskRepository(self.db_path)
        self.review_repository = ReviewRecordRepository(self.db_path)
        self.video_repository = VideoRepository(self.db_path)
        self.asr_repository = AsrRepository(self.db_path)
        self.cleanup_service = FileCleanupService()
        self.generation_adapter = generation_adapter or LipSyncGenerationAdapter(
            db_path=self.db_path,
            temp_dir=self.temp_dir,
            generated_dir=self.generated_dir,
        )
        self._heartbeat_last_logged_at: dict[str, float] = {}

    def _load_project_context(self, project_id: str):
        project = self.project_repository.get_project(project_id)
        if project is None:
            raise ValueError("对口型项目不存在")
        video = self.video_repository.get(project["base_video_id"])
        if video is None:
            raise ValueError("基础视频不存在")
        asr = self.asr_repository.get_by_video(project["base_video_id"])
        return project, video, asr

    def _resolve_script_text(self, candidate: dict):
        edited_content = str(candidate.get("edited_content") or "").strip()
        if candidate.get("is_edited") and edited_content:
            return edited_content
        return str(candidate.get("content") or "").strip()

    def _start_task_worker(self, task_id: str):
        run_in_background(self._run_task_generation, task_id)

    def _enqueue_task(self, task_id: str):
        worker_task_id = None
        task_to_return = None
        with LIP_SYNC_SCHEDULER_LOCK:
            task = self.task_repository.get_task(task_id)
            if task is None:
                return None
            active_task = self.task_repository.get_active_task()
            if active_task is not None:
                if task["status"] != "queued":
                    task = self.task_repository.update_task(task_id, status="queued")
                return task

            next_task = self.task_repository.get_next_waiting_task()
            if next_task is None:
                return task

            if next_task["id"] != task_id:
                if task["status"] != "queued":
                    task = self.task_repository.update_task(task_id, status="queued")
                worker_task_id = next_task["id"]
                self.task_repository.update_task(worker_task_id, status="starting")
                task_to_return = task
            else:
                task = self.task_repository.update_task(task_id, status="starting")
                worker_task_id = task_id
                task_to_return = task

        if worker_task_id is not None:
            self._start_task_worker(worker_task_id)
        return task_to_return

    def _schedule_next_task(self):
        worker_task_id = None
        with LIP_SYNC_SCHEDULER_LOCK:
            if self.task_repository.get_active_task() is not None:
                return None
            next_task = self.task_repository.get_next_waiting_task()
            if next_task is None:
                return None
            worker_task_id = next_task["id"]
            self.task_repository.update_task(worker_task_id, status="starting")

        if worker_task_id is not None:
            self._start_task_worker(worker_task_id)
        return self.task_repository.get_task(worker_task_id) if worker_task_id else None

    def _log_pending_heartbeat(self, *, task_id: str, stage: str, message: str, elapsed_sec: float | None):
        now = time.monotonic()
        last_logged_at = self._heartbeat_last_logged_at.get(task_id, 0.0)
        if now - last_logged_at < LIP_SYNC_HEARTBEAT_LOG_INTERVAL_SEC:
            return
        self._heartbeat_last_logged_at[task_id] = now
        log_fn = logger.warning if (elapsed_sec is not None and elapsed_sec >= LIP_SYNC_HEARTBEAT_WARN_AFTER_SEC) else logger.info
        log_fn(
            _format_elapsed_message(message, elapsed_sec),
            extra={
                "task_id": task_id,
                "stage": stage,
                "elapsed_sec": round(elapsed_sec, 1) if elapsed_sec is not None else "-",
            },
        )

    def create_project(
        self,
        *,
        role_id: str,
        base_video_id: str,
        prompt_text: str,
        product_doc_path: str,
    ):
        project = self.project_repository.create_project(
            role_id=role_id,
            base_video_id=base_video_id,
            prompt_text=prompt_text,
            product_doc_url=product_doc_path,
            status="draft",
        )
        logger.info(
            "对口型项目已创建: base_video_id=%s",
            base_video_id,
            extra={"task_id": project["id"], "stage": "lip_sync_project_created"},
        )
        return project

    def generate_candidates(self, project_id: str, *, count: int):
        #根据id查出来对口型项目记录，基础视频记录，基础视频的语音转文字结果
        project, video, asr = self._load_project_context(project_id)
        
        logger.info(
            "对口型候选生成开始: count=%s",
            count,
            extra={"task_id": project_id, "stage": "lip_sync_candidates_generating"},
        )
        #调用算法适配器生成候选文案。
        candidates = self.generation_adapter.generate_script_candidates(
            base_video_path=video["file_path"],
            base_video_asr_text=(asr or {}).get("full_text", ""),
            prompt_text=project["prompt_text"],
            product_doc_text=project["product_doc_url"],
            count=count,
        )
        created = self.candidate_repository.replace_candidates(project_id=project_id, candidates=candidates)
        project = self.project_repository.update_status(project_id, status="script_generated")
        logger.info(
            "对口型候选生成完成: candidates=%s",
            len(created),
            extra={"task_id": project_id, "stage": "lip_sync_candidates_generated"},
        )
        return {
            "project": project,
            "candidates": created,
        }

    def regenerate_candidate(self, project_id: str, candidate_id: str):
        project, video, asr = self._load_project_context(project_id)
        source_candidate = self.candidate_repository.get_candidate(candidate_id)
        if source_candidate is None or source_candidate["project_id"] != project_id:
            raise ValueError("候选文案不存在")

        regenerated = self.generation_adapter.regenerate_script_candidate(
            base_video_path=video["file_path"],
            base_video_asr_text=(asr or {}).get("full_text", ""),
            prompt_text=project["prompt_text"],
            product_doc_text=project["product_doc_url"],
            source_script_text=self._resolve_script_text(source_candidate),
        )
        return self.candidate_repository.update_candidate(
            candidate_id,
            content=regenerated["content"],
            char_count=regenerated["char_count"],
            estimated_tts_duration_sec=regenerated["estimated_tts_duration_sec"],
            edited_content=None,
            is_edited=False,
        )

    def edit_candidate(self, candidate_id: str, *, edited_content: str):
        return self.candidate_repository.update_candidate(
            candidate_id,
            edited_content=edited_content,
            is_edited=True,
        )

    def select_candidate(self, project_id: str, candidate_id: str):
        candidate = self.candidate_repository.get_candidate(candidate_id)
        if candidate is None or candidate["project_id"] != project_id:
            raise ValueError("候选文案不存在")
        updated = self.candidate_repository.update_candidate(candidate_id, is_selected=True)
        project = self.project_repository.update_status(project_id, status="script_selected")
        return {
            "project": project,
            "candidate": updated,
        }

    def create_task(
        self,
        *,
        project_id: str,
        selected_script_id: str,
        aspect_mode: str,
        resolution: str,
        subtitle_enabled: bool,
    ):
        project, video, _ = self._load_project_context(project_id)
        candidate = self.candidate_repository.get_candidate(selected_script_id)
        if candidate is None or candidate["project_id"] != project_id:
            raise ValueError("候选文案不存在")

        final_script_text = self._resolve_script_text(candidate)
        validation = self.generation_adapter.validate_script_tts_duration(
            base_video_path=video["file_path"],
            script_text=final_script_text,
        )
        if not validation.get("valid"):
            raise ValueError(
                f"TTS 时长超限，预计 {validation['estimated_tts_duration_sec']:.1f} 秒"
            )

        task = self.task_repository.create_task(
            project_id=project_id,
            role_id=project["role_id"],
            base_video_id=project["base_video_id"],
            selected_script_id=selected_script_id,
            final_script_text=final_script_text,
            aspect_mode=aspect_mode,
            resolution=resolution,
            subtitle_enabled=subtitle_enabled,
            status="pending",
            video_job_id=None,
        )
        self.project_repository.update_status(project_id, status="submitted")
        task = self._enqueue_task(task["id"]) or task
        logger.info(
            "对口型任务已创建: status=%s",
            task["status"],
            extra={"task_id": task["id"], "stage": "lip_sync_task_created"},
        )
        return task

    def _run_task_generation(self, task_id: str):
        try:
            while True:
                task = self.task_repository.get_task(task_id)
                if task is None or task["status"] in LIP_SYNC_TERMINAL_STATUSES:
                    return
                if task["status"] not in LIP_SYNC_ACTIVE_STATUSES:
                    return

                if task["status"] == "starting":
                    video = self.video_repository.get(task["base_video_id"])
                    if video is None:
                        self.task_repository.update_task(
                            task_id,
                            status="failed",
                            error_message="基础视频不存在",
                        )
                        return
                    try:
                        logger.info(
                            "对口型任务提交生成",
                            extra={"task_id": task_id, "stage": "lip_sync_submit_generation"},
                        )
                        submitted = self.generation_adapter.submit_generation(
                            task_id=task_id,
                            base_video_path=video["file_path"],
                            script_text=task["final_script_text"],
                            aspect_mode=task["aspect_mode"],
                            resolution=task["resolution"],
                            subtitle_enabled=bool(task["subtitle_enabled"]),
                        )
                    except Exception as exc:
                        logger.exception(
                            "对口型任务提交失败: %s",
                            str(exc),
                            extra={"task_id": task_id, "stage": "lip_sync_submit_failed"},
                        )
                        self.task_repository.update_task(
                            task_id,
                            status="failed",
                            error_message=str(exc),
                        )
                        return
                    task = self.task_repository.update_task(
                        task_id,
                        status="video_generating",
                        final_script_text=submitted["final_script_text"],
                        video_job_id=submitted["video_job_id"],
                        tts_audio_path=submitted["tts_audio_path"],
                    )

                result = self.generation_adapter.poll_generation(
                    task_id=task_id,
                    video_job_id=task["video_job_id"],
                )
                if result["status"] == "pending":
                    self._log_pending_heartbeat(
                        task_id=task_id,
                        stage="lip_sync_poll_pending",
                        message="对口型任务仍在生成中",
                        elapsed_sec=_elapsed_seconds_since(task.get("created_at")),
                    )
                    time.sleep(0.1)
                    continue
                if result["status"] == "success":
                    logger.info(
                        "对口型任务生成成功",
                        extra={"task_id": task_id, "stage": "lip_sync_poll_success"},
                    )
                    self.task_repository.update_task(
                        task_id,
                        status="success",
                        output_video_url=result["output_video_url"],
                    )
                    self.review_repository.create_pending(
                        source_type="lip_sync",
                        source_task_id=task_id,
                    )
                    return
                logger.error(
                    "对口型任务生成失败: %s",
                    str(result.get("message") or "视频生成失败"),
                    extra={"task_id": task_id, "stage": "lip_sync_poll_failed"},
                )
                self.task_repository.update_task(
                    task_id,
                    status="failed",
                    error_message=str(result.get("message") or "视频生成失败"),
                )
                return
        finally:
            self._schedule_next_task()

    def poll_task(self, task_id: str):
        task = self.task_repository.get_task(task_id)
        if task is None:
            raise ValueError("对口型任务不存在")
        if task["status"] not in LIP_SYNC_ACTIVE_STATUSES:
            return task
        if task["status"] == "starting":
            return task

        result = self.generation_adapter.poll_generation(
            task_id=task_id,
            video_job_id=task["video_job_id"],
        )
        if result["status"] == "pending":
            self._log_pending_heartbeat(
                task_id=task_id,
                stage="lip_sync_poll_pending",
                message="对口型任务仍在生成中",
                elapsed_sec=_elapsed_seconds_since(task.get("created_at")),
            )
            return task
        if result["status"] == "success":
            logger.info(
                "对口型任务生成成功",
                extra={"task_id": task_id, "stage": "lip_sync_poll_success"},
            )
            task = self.task_repository.update_task(
                task_id,
                status="success",
                output_video_url=result["output_video_url"],
            )
            self.review_repository.create_pending(
                source_type="lip_sync",
                source_task_id=task_id,
            )
            self._schedule_next_task()
            return task
        logger.error(
            "对口型任务生成失败: %s",
            str(result.get("message") or "视频生成失败"),
            extra={"task_id": task_id, "stage": "lip_sync_poll_failed"},
        )
        task = self.task_repository.update_task(
            task_id,
            status="failed",
            error_message=str(result.get("message") or "视频生成失败"),
        )
        self._schedule_next_task()
        return task

    def get_task_detail(self, task_id: str):
        return {
            "task": self.task_repository.get_task(task_id),
        }

    def cancel_task(self, task_id: str):
        task = self.task_repository.get_task(task_id)
        if task is None:
            raise ValueError("对口型任务不存在")
        if task["status"] == "success":
            return task
        self.cleanup_service.remove_paths([task.get("tts_audio_path"), task.get("output_video_url")])
        cancelled = self.task_repository.update_task(task_id, status="cancelled")
        self.project_repository.update_status(task["project_id"], status="cancelled")
        self._schedule_next_task()
        return cancelled
