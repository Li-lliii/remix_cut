from pathlib import Path

from platform_app.repositories.lip_sync_repository import LipSyncTaskRepository
from platform_app.repositories.preprocess_job_repository import PreprocessJobRepository
from platform_app.repositories.remix_repository import RemixTaskRepository
from platform_app.repositories.video_repository import VideoRepository


class TaskRecordDeleteService:
    TERMINAL_PREPROCESS_STATUSES = {"success", "failed", "cancelled"}
    TERMINAL_REMIX_STATUSES = {"success", "partial_success", "failed", "cancelled"}
    TERMINAL_LIP_SYNC_STATUSES = {"success", "failed", "cancelled"}

    def __init__(self, *, db_path: Path):
        self.db_path = Path(db_path)
        self.preprocess_job_repository = PreprocessJobRepository(self.db_path)
        self.remix_task_repository = RemixTaskRepository(self.db_path)
        self.lip_sync_task_repository = LipSyncTaskRepository(self.db_path)
        self.video_repository = VideoRepository(self.db_path)

    def _ensure_terminal(self, status: str, allowed: set[str], *, label: str):
        if status not in allowed:
            raise ValueError(f"{label} 运行中任务不能删除")

    def delete_preprocess_job_record(self, job_id: str, *, role_id: str):
        job = self.preprocess_job_repository.get(job_id)
        if job is None:
            raise ValueError("预处理任务不存在")
        video = self.video_repository.get(job["role_video_id"], include_deleted=True)
        if video is None or video["role_id"] != role_id:
            raise ValueError("预处理任务不存在")
        self._ensure_terminal(job["status"], self.TERMINAL_PREPROCESS_STATUSES, label="预处理")
        return self.preprocess_job_repository.soft_delete(job_id)

    def delete_remix_task_record(self, task_id: str, *, role_id: str):
        task = self.remix_task_repository.get_task(task_id)
        if task is None or task["role_id"] != role_id:
            raise ValueError("混剪任务不存在")
        self._ensure_terminal(task["status"], self.TERMINAL_REMIX_STATUSES, label="混剪")
        return self.remix_task_repository.soft_delete(task_id)

    def delete_lip_sync_task_record(self, task_id: str, *, role_id: str):
        task = self.lip_sync_task_repository.get_task(task_id)
        if task is None or task["role_id"] != role_id:
            raise ValueError("对口型任务不存在")
        self._ensure_terminal(task["status"], self.TERMINAL_LIP_SYNC_STATUSES, label="对口型")
        return self.lip_sync_task_repository.soft_delete(task_id)

    def batch_delete_preprocess_job_records(self, *, role_id: str, job_ids: list[str]):
        deleted = []
        failed = []
        for job_id in job_ids:
            try:
                deleted.append(self.delete_preprocess_job_record(job_id, role_id=role_id))
            except ValueError:
                failed.append(job_id)
        return {"deleted_count": len(deleted), "failed_count": len(failed), "failed_ids": failed}

    def batch_delete_remix_task_records(self, *, role_id: str, task_ids: list[str]):
        deleted = []
        failed = []
        for task_id in task_ids:
            try:
                deleted.append(self.delete_remix_task_record(task_id, role_id=role_id))
            except ValueError:
                failed.append(task_id)
        return {"deleted_count": len(deleted), "failed_count": len(failed), "failed_ids": failed}

    def batch_delete_lip_sync_task_records(self, *, role_id: str, task_ids: list[str]):
        deleted = []
        failed = []
        for task_id in task_ids:
            try:
                deleted.append(self.delete_lip_sync_task_record(task_id, role_id=role_id))
            except ValueError:
                failed.append(task_id)
        return {"deleted_count": len(deleted), "failed_count": len(failed), "failed_ids": failed}
