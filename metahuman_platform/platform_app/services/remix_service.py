from pathlib import Path
import time
import logging
from datetime import datetime, timezone

from platform_app.repositories.remix_repository import RemixSegmentRepository, RemixTaskRepository
from platform_app.repositories.review_repository import ReviewRecordRepository
from platform_app.services.file_cleanup_service import FileCleanupService
from platform_app.services.preprocess_service import PreprocessService
from platform_app.services.remix_generation_adapter import RemixGenerationAdapter


logger = logging.getLogger(__name__)

HEARTBEAT_LOG_INTERVAL_SEC = 30.0
HEARTBEAT_WARN_AFTER_SEC = 10 * 60.0


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


class RemixService:
    def __init__(
        self,
        *,
        db_path: Path,
        temp_dir: Path,
        generated_dir: Path,
        preprocess_service: PreprocessService,
        generation_adapter=None,
    ):
        self.db_path = Path(db_path)
        self.temp_dir = Path(temp_dir)
        self.generated_dir = Path(generated_dir)
        self.preprocess_service = preprocess_service
        self.segment_repository = RemixSegmentRepository(self.db_path)
        self.task_repository = RemixTaskRepository(self.db_path)
        self.review_repository = ReviewRecordRepository(self.db_path)
        self.cleanup_service = FileCleanupService()
        self.generation_adapter = generation_adapter or RemixGenerationAdapter(
            temp_dir=self.temp_dir,
            generated_dir=self.generated_dir,
        )
        # 仅用于日志心跳节流（不入库），避免每次 poll 都刷屏。
        self._heartbeat_last_logged_at: dict[str, float] = {}

    def _load_product_doc_text(self, product_doc_url: str) -> str:
        raw = str(product_doc_url or "").strip()
        if not raw:
            return ""
        if "\n" in raw or "\r" in raw or len(raw) > 240:
            return raw
        candidate = Path(raw).expanduser()
        try:
            if candidate.exists() and candidate.is_file():
                return candidate.read_text(encoding="utf-8")
        except OSError:
            return raw
        return raw

    def create_task(
        self,
        *,
        role_id: str,
        source_video_id: str,
        prompt_text: str,
        product_doc_path: str,
        target_count: int,
        is_max_mode: bool,
        aspect_mode: str,
        resolution: str,
        subtitle_enabled: bool,
    ):
        preprocess_result = self.preprocess_service.start_preprocess(source_video_id)
        initial_status = "ready" if preprocess_result["job"]["status"] == "success" else "pending_preprocess"
        task = self.task_repository.create_task(
            role_id=role_id,
            source_video_id=source_video_id,
            prompt_text=prompt_text,
            product_doc_url=product_doc_path,
            target_count=target_count,
            is_max_mode=is_max_mode,
            aspect_mode=aspect_mode,
            resolution=resolution,
            subtitle_enabled=subtitle_enabled,
            status=initial_status,
        )
        logger.info(
            "混剪任务已创建: status=%s source_video_id=%s target_count=%s is_max_mode=%s",
            task["status"],
            source_video_id,
            target_count,
            bool(is_max_mode),
            extra={"task_id": task["id"], "stage": "remix_task_created"},
        )
        return task

    def process_task(self, task_id: str):
        task = self.task_repository.get_task(task_id)
        if task is None:
            raise ValueError("混剪任务不存在")
        if task["status"] in {"success", "partial_success", "failed", "cancelled"}:
            return task
        try:
            logger.info(
                "混剪任务开始处理: status=%s",
                task["status"],
                extra={"task_id": task_id, "stage": "remix_process_start"},
            )

            preprocess_result = self.preprocess_service.start_preprocess(task["source_video_id"])
            if preprocess_result["job"]["status"] != "success":
                preprocess_result = self.preprocess_service.run_job(preprocess_result["job"]["id"])
            if preprocess_result["job"]["status"] != "success":
                status = "cancelled" if preprocess_result["job"]["status"] == "cancelled" else "failed"
                message = preprocess_result["job"].get("error_message") or "预处理失败，无法创建混剪任务"
                logger.error(
                    "混剪任务预处理失败: status=%s message=%s",
                    preprocess_result["job"]["status"],
                    message,
                    extra={"task_id": task_id, "stage": "remix_preprocess_failed"},
                )
                return self.task_repository.update_task_status(task_id, status=status, error_message=message)
            logger.info(
                "混剪任务预处理完成: segments=%s",
                len(self.segment_repository.list_by_video(task["source_video_id"])),
                extra={"task_id": task_id, "stage": "remix_preprocess_success"},
            )

            segments = self.segment_repository.list_by_video(task["source_video_id"])
            selected_segments = segments if task["is_max_mode"] else segments[: task["target_count"]]
            if not selected_segments:
                return self.task_repository.update_task_status(
                    task_id,
                    status="failed",
                    error_message="预处理未产出可用混剪片段",
                )
            items = self.task_repository.list_items(task_id)
            if not items:
                items = self.task_repository.create_items(task_id, [segment["id"] for segment in selected_segments])
            if not items:
                return self.task_repository.update_task_status(
                    task_id,
                    status="failed",
                    error_message="未创建任何混剪子任务",
                )

            self.task_repository.update_task_status(task_id, status="running")
            logger.info(
                "混剪子任务已准备: items=%s segments=%s",
                len(items),
                len(selected_segments),
                extra={"task_id": task_id, "stage": "remix_items_ready"},
            )
            segment_map = {segment["id"]: segment for segment in selected_segments}
            product_doc_text = self._load_product_doc_text(task["product_doc_url"])
            for item in items:
                if item["status"] in {"success", "failed", "cancelled"}:
                    continue
                segment = segment_map.get(item["segment_id"])
                if segment is None:
                    continue
                try:
                    self.task_repository.update_item(item["id"], status="rewriting")
                    logger.info(
                        "混剪子任务进入改写",
                        extra={"task_id": task_id, "item_id": item["id"], "stage": "remix_item_rewriting"},
                    )
                    self.task_repository.update_item(item["id"], status="tts_generating")
                    logger.info(
                        "混剪子任务进入 TTS",
                        extra={"task_id": task_id, "item_id": item["id"], "stage": "remix_item_tts_generating"},
                    )
                    logger.info(
                        "混剪子任务提交视频生成",
                        extra={"task_id": task_id, "item_id": item["id"], "stage": "remix_submit_generation"},
                    )
                    submitted = self.generation_adapter.submit_generation(
                        task_id=task_id,
                        item_id=item["id"],
                        segment_file_path=segment["segment_file_path"],
                        segment_asr_text=segment["asr_text"],
                        prompt_text=task["prompt_text"],
                        product_doc_text=product_doc_text,
                        aspect_mode=task["aspect_mode"],
                        resolution=task["resolution"],
                        subtitle_enabled=bool(task["subtitle_enabled"]),
                    )
                    self.task_repository.update_item(
                        item["id"],
                        status="video_generating",
                        comfy_prompt_id=submitted["prompt_id"],
                        rewritten_text=submitted["rewritten_text"],
                        tts_audio_path=submitted["tts_audio_path"],
                    )
                    logger.info(
                        "混剪子任务已进入视频生成: prompt_id=%s",
                        submitted["prompt_id"],
                        extra={
                            "task_id": task_id,
                            "item_id": item["id"],
                            "prompt_id": submitted["prompt_id"],
                            "stage": "remix_video_generating",
                        },
                    )
                except Exception as exc:
                    logger.exception(
                        "混剪子任务提交失败: %s",
                        str(exc),
                        extra={"task_id": task_id, "item_id": item["id"], "stage": "remix_item_failed"},
                    )
                    self.task_repository.update_item(
                        item["id"],
                        status="failed",
                        error_message=str(exc),
                    )

            task = self.task_repository.refresh_counts(task_id)
            if task["running_count"] > 0:
                return self.task_repository.update_task_status(task_id, status="running")
            return self._finalize_task_status(task_id)
        except Exception as exc:
            logger.exception(
                "混剪任务处理异常: %s",
                str(exc),
                extra={"task_id": task_id, "stage": "remix_process_failed"},
            )
            return self.task_repository.update_task_status(
                task_id,
                status="failed",
                error_message=str(exc),
            )

    def _finalize_task_status(self, task_id: str):
        task = self.task_repository.refresh_counts(task_id)
        if task["running_count"] > 0:
            return self.task_repository.update_task_status(task_id, status="running")
        if task["success_count"] > 0 and task["failed_count"] == 0:
            final = self.task_repository.update_task_status(task_id, status="success")
            logger.info(
                "混剪任务完成: status=success success_count=%s failed_count=%s",
                final["success_count"],
                final["failed_count"],
                extra={"task_id": task_id, "stage": "remix_task_finished"},
            )
            return final
        if task["success_count"] > 0 and task["failed_count"] > 0:
            final = self.task_repository.update_task_status(task_id, status="partial_success")
            logger.warning(
                "混剪任务完成: status=partial_success success_count=%s failed_count=%s",
                final["success_count"],
                final["failed_count"],
                extra={"task_id": task_id, "stage": "remix_task_finished"},
            )
            return final
        if task["failed_count"] > 0:
            final = self.task_repository.update_task_status(task_id, status="failed")
            logger.error(
                "混剪任务完成: status=failed failed_count=%s",
                final["failed_count"],
                extra={"task_id": task_id, "stage": "remix_task_finished"},
            )
            return final
        final = self.task_repository.update_task_status(
            task_id,
            status="failed",
            error_message="未生成任何混剪子任务",
        )
        logger.error(
            "混剪任务完成: status=failed message=%s",
            final.get("error_message"),
            extra={"task_id": task_id, "stage": "remix_task_finished"},
        )
        return final

    def run_task(self, task_id: str, *, poll_interval_sec: float = 3.0):
        logger.info(
            "混剪任务后台运行启动: poll_interval_sec=%s",
            poll_interval_sec,
            extra={"task_id": task_id, "stage": "remix_run_started"},
        )
        task = self.process_task(task_id)
        terminal_states = {"success", "partial_success", "failed", "cancelled"}
        while task is not None and task["status"] not in terminal_states:
            time.sleep(poll_interval_sec)
            task = self.poll_task(task_id)
        if task is not None and task.get("status") in terminal_states:
            logger.info(
                "混剪任务后台运行结束: status=%s",
                task.get("status"),
                extra={"task_id": task_id, "stage": "remix_task_finished"},
            )
        return task

    def poll_task(self, task_id: str):
        task = self.task_repository.get_task(task_id)
        if task is None:
            raise ValueError("混剪任务不存在")
        if task["status"] in {"success", "partial_success", "failed", "cancelled"}:
            return task
        if task["status"] in {"pending_preprocess", "ready"}:
            return task

        items = self.task_repository.list_items(task_id)
        for item in items:
            if item["status"] != "video_generating":
                continue
            prompt_id = str(item.get("comfy_prompt_id") or "").strip()
            if not prompt_id:
                self.task_repository.update_item(
                    item["id"],
                    status="failed",
                    error_message="缺少 ComfyUI prompt_id，无法轮询生成结果",
                )
                logger.error(
                    "混剪子任务轮询失败: 缺少 prompt_id",
                    extra={"task_id": task_id, "item_id": item["id"], "stage": "remix_poll_failed"},
                )
                continue
            try:
                result = self.generation_adapter.poll_generation(task_id=task_id, prompt_id=prompt_id)
            except Exception as exc:
                logger.exception(
                    "混剪子任务轮询异常: %s",
                    str(exc),
                    extra={"task_id": task_id, "item_id": item["id"], "prompt_id": prompt_id, "stage": "remix_poll_failed"},
                )
                self.task_repository.update_item(
                    item["id"],
                    status="failed",
                    comfy_prompt_id=prompt_id,
                    rewritten_text=item["rewritten_text"],
                    tts_audio_path=item["tts_audio_path"],
                    error_message=str(exc),
                )
                continue

            if result["status"] == "pending":
                now = time.monotonic()
                last = self._heartbeat_last_logged_at.get(item["id"], 0.0)
                elapsed = _elapsed_seconds_since(item.get("created_at"))
                should_log = (now - last) >= HEARTBEAT_LOG_INTERVAL_SEC or last == 0.0
                if should_log:
                    self._heartbeat_last_logged_at[item["id"]] = now
                    level = logging.WARNING if (elapsed is not None and elapsed >= HEARTBEAT_WARN_AFTER_SEC) else logging.INFO
                    logger.log(
                        level,
                        "混剪子任务仍在生成中: elapsed_sec=%s",
                        None if elapsed is None else round(elapsed, 1),
                        extra={
                            "task_id": task_id,
                            "item_id": item["id"],
                            "prompt_id": prompt_id,
                            "stage": "remix_poll_pending",
                        },
                    )
                continue
            if result["status"] == "success":
                logger.info(
                    "混剪子任务生成成功",
                    extra={"task_id": task_id, "item_id": item["id"], "prompt_id": prompt_id, "stage": "remix_poll_success"},
                )
                final_item = self.task_repository.update_item(
                    item["id"],
                    status="success",
                    comfy_prompt_id=prompt_id,
                    rewritten_text=item["rewritten_text"],
                    tts_audio_path=item["tts_audio_path"],
                    output_video_url=result["output_video_url"],
                )
                self.review_repository.create_pending(
                    source_type="remix",
                    source_task_id=final_item["id"],
                )
                continue

            logger.error(
                "混剪子任务生成失败: %s",
                str(result.get("message") or "视频生成失败"),
                extra={"task_id": task_id, "item_id": item["id"], "prompt_id": prompt_id, "stage": "remix_poll_failed"},
            )
            self.task_repository.update_item(
                item["id"],
                status="failed",
                comfy_prompt_id=prompt_id,
                rewritten_text=item["rewritten_text"],
                tts_audio_path=item["tts_audio_path"],
                error_message=str(result.get("message") or "视频生成失败"),
            )

        return self._finalize_task_status(task_id)

    def get_task_detail(self, task_id: str):
        self.poll_task(task_id)
        return {
            "task": self.task_repository.get_task(task_id),
            "items": self.task_repository.list_items(task_id),
        }

    def list_tasks(self):
        tasks = self.task_repository.list_tasks()
        for task in tasks:
            if task["status"] not in {"success", "partial_success", "failed", "cancelled"}:
                self.poll_task(task["id"])
        return self.task_repository.list_tasks()

    def cancel_task(self, task_id: str):
        task = self.task_repository.get_task(task_id)
        if task is None:
            raise ValueError("混剪任务不存在")
        if task["status"] in {"success", "partial_success", "failed", "cancelled"}:
            return task
        items = self.task_repository.list_items(task_id)
        for item in items:
            self.cleanup_service.remove_paths([item["tts_audio_path"], item["output_video_url"]])
            self.task_repository.update_item(item["id"], status="cancelled")
        return self.task_repository.update_task_status(task_id, status="cancelled")
