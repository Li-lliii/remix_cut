from pathlib import Path

from platform_app.repositories.preprocess_job_repository import PreprocessJobRepository
from platform_app.repositories.lip_sync_repository import LipSyncTaskRepository
from platform_app.repositories.remix_repository import RemixTaskRepository
from platform_app.repositories.smart_clip_repository import SmartClipRepository
from platform_app.repositories.role_repository import RoleRepository
from platform_app.repositories.video_repository import VideoRepository


class TaskQueryService:
    def __init__(self, *, db_path: Path):
        self.db_path = Path(db_path)
        self.role_repository = RoleRepository(self.db_path)
        self.video_repository = VideoRepository(self.db_path)
        self.preprocess_job_repository = PreprocessJobRepository(self.db_path)
        self.remix_task_repository = RemixTaskRepository(self.db_path)
        self.lip_sync_task_repository = LipSyncTaskRepository(self.db_path)
        self.smart_clip_repository = SmartClipRepository(self.db_path)

    def list_preprocess_jobs(self, role_id: str | None = None):
        role_cache = {role["id"]: role for role in self.role_repository.list()}
        videos = self.video_repository.list_all()
        if role_id:
            videos = [video for video in videos if video["role_id"] == role_id]
        video_cache = {video["id"]: video for video in videos}
        jobs = []
        for video in video_cache.values():
            for job in self.preprocess_job_repository.list_by_video(video["id"]):
                job["role_id"] = video["role_id"]
                job["role_name"] = role_cache.get(video["role_id"], {}).get("name", "-")
                job["video_title"] = video.get("title", "-")
                jobs.append(job)
        return jobs

    def list_asr_records(self, role_id: str | None = None):
        role_cache = {role["id"]: role for role in self.role_repository.list()}
        videos = self.video_repository.list_all()
        if role_id:
            videos = [video for video in videos if video["role_id"] == role_id]
        records = []
        for video in videos:
            records.append(
                {
                    "record_type": "asr",
                    "video_id": video["id"],
                    "role_id": video["role_id"],
                    "role_name": role_cache.get(video["role_id"], {}).get("name", "-"),
                    "video_title": video.get("title", "-"),
                    "uploaded_at": video.get("uploaded_at"),
                    "asr_status": video.get("asr_status", "pending"),
                    "asr_error_message": video.get("asr_error_message"),
                }
            )
        return records

    def list_remix_tasks(self, role_id: str | None = None):
        role_cache = {role["id"]: role for role in self.role_repository.list()}
        video_cache = {video["id"]: video for video in self.video_repository.list_all()}
        tasks = self.remix_task_repository.list_tasks()
        if role_id:
            tasks = [task for task in tasks if task["role_id"] == role_id]
        rows = []
        for task in tasks:
            video = video_cache.get(task["source_video_id"], {})
            task["role_name"] = role_cache.get(task["role_id"], {}).get("name", "-")
            task["video_title"] = video.get("title", task["source_video_id"][:8])
            task["task_type"] = "remix"
            rows.append(task)
        rows.extend(self.list_smart_clip_tasks(role_id=role_id))
        return rows

    def list_smart_clip_tasks(self, role_id: str | None = None):
        role_cache = {role["id"]: role for role in self.role_repository.list()}
        projects = []
        for role in role_cache.values():
            if role_id and role["id"] != role_id:
                continue
            projects.extend(self.smart_clip_repository.list_projects_by_role(role["id"]))
        for project in projects:
            project["task_type"] = "smart_clip"
            project["project_id"] = project["id"]
            project["role_name"] = role_cache.get(project["role_id"], {}).get("name", "-")
            project["video_title"] = project.get("source_video_title") or project["source_video_id"][:8]
            project["source_video_title"] = project.get("source_video_title") or project["video_title"]
            project["progress_summary"] = self._build_smart_clip_progress_summary(project)
        return projects

    def _build_smart_clip_progress_summary(self, project: dict) -> str:
        status = str(project.get("status") or "")
        stage = str(project.get("stage") or "")
        export_total = int(project.get("export_total_count") or 0)
        export_current = int(project.get("export_current_index") or 0)
        export_completed = int(project.get("export_completed_count") or 0)
        candidate_count = int(project.get("candidate_clip_count") or 0)
        if status == "analyzing" or stage == "classifying":
            total_asr = int(project.get("total_asr_segments") or 0)
            return f"候选分析中，已读取 {total_asr} 段语音"
        if status == "ready":
            return f"已生成 {candidate_count} 个候选切片"
        if status == "exporting":
            current = export_current or 1
            return f"共 {export_total} 个候选切片，正在导出第 {current} 个"
        if status == "success":
            return f"已导出 {export_completed} 个切片视频"
        if status == "failed":
            return project.get("error_message") or "智能切片失败"
        return "等待处理"

    def list_lip_sync_tasks(self, role_id: str | None = None):
        role_cache = {role["id"]: role for role in self.role_repository.list()}
        video_cache = {video["id"]: video for video in self.video_repository.list_all()}
        tasks = self.lip_sync_task_repository.list_tasks()
        if role_id:
            tasks = [task for task in tasks if task["role_id"] == role_id]
        for task in tasks:
            video = video_cache.get(task["base_video_id"], {})
            task["role_name"] = role_cache.get(task["role_id"], {}).get("name", "-")
            task["video_title"] = video.get("title", task["base_video_id"][:8])
        return tasks
