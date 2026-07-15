from pathlib import Path
import logging

from platform_app.repositories.asr_repository import AsrRepository
from platform_app.repositories.preprocess_job_repository import PreprocessJobRepository
from platform_app.repositories.remix_repository import RemixSegmentRepository
from platform_app.repositories.video_repository import VideoRepository
from platform_app.services.file_cleanup_service import FileCleanupService
from platform_app.services.preprocess_adapter import PreprocessAdapter


logger = logging.getLogger(__name__)


class PreprocessService:
    def __init__(self, *, db_path: Path, temp_dir: Path, work_dir: Path | None = None, preprocess_adapter=None):
        self.db_path = Path(db_path)
        self.temp_dir = Path(temp_dir)
        self.work_dir = Path(work_dir) if work_dir else self.temp_dir.parent / "work"
        self.video_repository = VideoRepository(self.db_path)
        self.asr_repository = AsrRepository(self.db_path)
        self.job_repository = PreprocessJobRepository(self.db_path)
        self.segment_repository = RemixSegmentRepository(self.db_path)
        self.cleanup_service = FileCleanupService()
        self.preprocess_adapter = preprocess_adapter or PreprocessAdapter(work_dir=self.work_dir)

    def start_preprocess(self, video_id: str):
        existing_segments = self.segment_repository.list_by_video(video_id)
        latest_job = self.job_repository.latest_by_video(video_id)
        if existing_segments and latest_job and latest_job["status"] == "success":
            logger.info(
                "预处理复用成功结果: preprocess_job_id=%s segments=%s",
                latest_job["id"],
                len(existing_segments),
                extra={"task_id": latest_job["id"], "stage": "preprocess_reused"},
            )
            return {"reused": True, "started": False, "job": latest_job, "segments": existing_segments}
        if latest_job and latest_job["status"] in {"pending", "running"}:
            logger.info(
                "预处理已有运行中任务: preprocess_job_id=%s status=%s progress=%s",
                latest_job["id"],
                latest_job["status"],
                latest_job.get("progress"),
                extra={"task_id": latest_job["id"], "stage": "preprocess_already_running"},
            )
            return {"reused": False, "started": False, "job": latest_job, "segments": []}

        video = self.video_repository.get(video_id)
        if video is None:
            raise ValueError("视频不存在")
        asr_result = self.asr_repository.get_by_video(video_id)
        if asr_result is None:
            raise ValueError("视频缺少 ASR 结果")

        job = self.job_repository.create(role_video_id=video_id, job_type="remix_preprocess")
        running_job = self.job_repository.update_status(job["id"], status="running", progress=20)
        logger.info(
            "预处理任务启动: preprocess_job_id=%s video_id=%s progress=%s",
            running_job["id"],
            video_id,
            running_job.get("progress"),
            extra={"task_id": running_job["id"], "stage": "preprocess_job_started"},
        )
        return {"reused": False, "started": True, "job": running_job, "segments": []}

    def run_job(self, job_id: str):
        job = self.job_repository.get(job_id)
        if job is None:
            raise ValueError("预处理任务不存在")
        if job["status"] in {"success", "failed", "cancelled"}:
            logger.info(
                "预处理任务已结束: preprocess_job_id=%s status=%s",
                job_id,
                job["status"],
                extra={"task_id": job_id, "stage": "preprocess_job_terminal"},
            )
            return {
                "reused": job["status"] == "success",
                "started": False,
                "job": job,
                "segments": self.segment_repository.list_by_video(job["role_video_id"]),
            }
        video = self.video_repository.get(job["role_video_id"])
        if video is None:
            raise ValueError("视频不存在")
        asr_result = self.asr_repository.get_by_video(job["role_video_id"])
        if asr_result is None:
            raise ValueError("视频缺少 ASR 结果")

        logger.info(
            "预处理任务开始执行: preprocess_job_id=%s video_id=%s",
            job_id,
            job["role_video_id"],
            extra={"task_id": job_id, "stage": "preprocess_run_started"},
        )
        try:
            segments = self.preprocess_adapter.build_segments(
                video_id=job["role_video_id"],
                video_path=video["file_path"],
                asr_full_text=asr_result["full_text"],
                asr_segments=asr_result["segments"],
            )
        except Exception as exc:
            logger.exception(
                "预处理任务执行失败: %s",
                str(exc),
                extra={"task_id": job_id, "stage": "preprocess_job_failed"},
            )
            raise
        stored_segments = self.segment_repository.replace_for_video(
            role_id=video["role_id"],
            source_video_id=job["role_video_id"],
            segments=segments,
        )
        final_job = self.job_repository.update_status(job["id"], status="success", progress=100)
        logger.info(
            "预处理任务完成: preprocess_job_id=%s segments=%s",
            job_id,
            len(stored_segments),
            extra={"task_id": job_id, "stage": "preprocess_job_success"},
        )
        return {"reused": False, "job": final_job, "segments": stored_segments}

    def ensure_preprocess(self, video_id: str):
        result = self.start_preprocess(video_id)
        if result["job"]["status"] == "success":
            return result
        return self.run_job(result["job"]["id"])

    def cancel_job(self, job_id: str):
        job = self.job_repository.get(job_id)
        if job is None:
            raise ValueError("预处理任务不存在")
        if job["status"] in {"success", "failed", "cancelled"}:
            return job
        segments = self.segment_repository.list_by_video(job["role_video_id"])
        self.cleanup_service.remove_paths([segment["segment_file_path"] for segment in segments])
        self.segment_repository.delete_by_video(job["role_video_id"])
        return self.job_repository.update_status(job_id, status="cancelled", progress=job["progress"])

    def list_jobs(self):
        jobs = []
        for video in self.video_repository.list_all():
            jobs.extend(self.job_repository.list_by_video(video["id"]))
        return jobs
