from pathlib import Path

from platform_app.repositories.lip_sync_repository import LipSyncTaskRepository
from platform_app.repositories.remix_repository import RemixTaskRepository
from platform_app.repositories.role_repository import RoleRepository
from platform_app.services.file_cleanup_service import FileCleanupService
from platform_app.repositories.video_repository import VideoRepository


class FinalVideoService:
    def __init__(self, *, db_path: Path):
        self.db_path = Path(db_path)
        self.role_repository = RoleRepository(self.db_path)
        self.video_repository = VideoRepository(self.db_path)
        self.remix_task_repository = RemixTaskRepository(self.db_path)
        self.lip_sync_task_repository = LipSyncTaskRepository(self.db_path)
        self.file_cleanup_service = FileCleanupService()

    def _build_role_cache(self) -> dict[str, dict]:
        return {role["id"]: role for role in self.role_repository.list()}

    def _build_video_cache(self) -> dict[str, dict]:
        return {video["id"]: video for video in self.video_repository.list_all()}

    def _match_query(self, value: str, keyword: str) -> bool:
        if not keyword:
            return True
        return keyword in str(value or "").lower()

    def _build_remix_rows(
        self,
        *,
        role_cache: dict[str, dict],
        video_cache: dict[str, dict],
        role_id: str | None,
        query: str,
    ) -> list[dict]:
        rows: list[dict] = []
        # 任务记录可能被用户在任务页隐藏（deleted_at），但成片预览仍需可见，
        # 因此这里使用包含已软删除任务的全量查询。
        for task in self.remix_task_repository.list_tasks(include_deleted=True):
            if task["status"] not in {"success", "partial_success"}:
                continue
            if role_id and task["role_id"] != role_id:
                continue
            video = video_cache.get(task["source_video_id"])
            if video is None:
                continue
            source_title = str(video.get("title") or "")
            if not self._match_query(source_title, query):
                continue
            role_name = role_cache.get(task["role_id"], {}).get("name", "-")
            for item in self.remix_task_repository.list_items(task["id"]):
                if item["status"] != "success" or not item.get("output_video_url") or item.get("final_deleted_at"):
                    continue
                rows.append(
                    {
                        "id": f"remix:{item['id']}",
                        "source_type": "remix",
                        "source_task_id": item["id"],
                        "role_id": task["role_id"],
                        "role_name": role_name,
                        "source_video_id": task["source_video_id"],
                        "source_video_title": source_title,
                        "output_video_url": item["output_video_url"],
                        "created_at": item["created_at"],
                        "status": item["status"],
                        "summary_text": item.get("rewritten_text") or "",
                    }
                )
        return rows

    def _build_lip_sync_rows(
        self,
        *,
        role_cache: dict[str, dict],
        video_cache: dict[str, dict],
        role_id: str | None,
        query: str,
    ) -> list[dict]:
        rows: list[dict] = []
        # 同 remix：成片预览不受任务记录软删除影响。
        for task in self.lip_sync_task_repository.list_tasks(include_deleted=True):
            if task["status"] != "success" or not task.get("output_video_url") or task.get("final_deleted_at"):
                continue
            if role_id and task["role_id"] != role_id:
                continue
            video = video_cache.get(task["base_video_id"])
            if video is None:
                continue
            source_title = str(video.get("title") or "")
            if not self._match_query(source_title, query):
                continue
            role_name = role_cache.get(task["role_id"], {}).get("name", "-")
            rows.append(
                {
                    "id": f"lip_sync:{task['id']}",
                    "source_type": "lip_sync",
                    "source_task_id": task["id"],
                    "role_id": task["role_id"],
                    "role_name": role_name,
                    "source_video_id": task["base_video_id"],
                    "source_video_title": source_title,
                    "output_video_url": task["output_video_url"],
                    "created_at": task["created_at"],
                    "status": task["status"],
                    "summary_text": task.get("final_script_text") or "",
                }
            )
        return rows

    def get_output_video_path(self, *, item_id: str, source_type: str) -> Path | None:
        source = str(source_type or "").strip().lower()
        raw_id = str(item_id or "").strip()
        if source == "remix":
            target_id = raw_id.split("remix:", 1)[-1]
            item = self.remix_task_repository.get_item(target_id)
            if not item or not item.get("output_video_url") or item.get("final_deleted_at"):
                return None
            return Path(item["output_video_url"]).expanduser()
        if source == "lip_sync":
            target_id = raw_id.split("lip_sync:", 1)[-1]
            task = self.lip_sync_task_repository.get_task(target_id)
            if task and task.get("output_video_url") and not task.get("final_deleted_at"):
                return Path(task["output_video_url"]).expanduser()
            return None
        return None

    def list_final_videos(
        self,
        *,
        role_id: str | None = None,
        q: str | None = None,
        source_type: str | None = None,
    ) -> list[dict]:
        query = str(q or "").strip().lower()
        source_type_value = str(source_type or "").strip().lower()

        role_cache = self._build_role_cache()
        video_cache = self._build_video_cache()

        rows: list[dict] = []
        if source_type_value in {"", "remix"}:
            rows.extend(
                self._build_remix_rows(
                    role_cache=role_cache,
                    video_cache=video_cache,
                    role_id=role_id,
                    query=query,
                )
            )
        if source_type_value in {"", "lip_sync"}:
            rows.extend(
                self._build_lip_sync_rows(
                    role_cache=role_cache,
                    video_cache=video_cache,
                    role_id=role_id,
                    query=query,
                )
            )

        rows.sort(key=lambda item: item["created_at"], reverse=True)
        return rows

    def delete_final_video(self, *, item_id: str, source_type: str, role_id: str):
        source = str(source_type or "").strip().lower()
        raw_id = str(item_id or "").strip()
        if source == "remix":
            target_id = raw_id.split("remix:", 1)[-1]
            item = self.remix_task_repository.get_item(target_id)
            if item is None or item.get("final_deleted_at") or item.get("status") != "success":
                raise ValueError("成片不存在")
            task = self.remix_task_repository.get_task(item["remix_task_id"])
            if task is None or task["role_id"] != role_id:
                raise ValueError("成片不存在")
            if not item.get("output_video_url"):
                raise ValueError("成片不存在")
            self.file_cleanup_service.remove_paths([item.get("output_video_url")])
            return self.remix_task_repository.soft_delete_item(target_id)
        if source == "lip_sync":
            target_id = raw_id.split("lip_sync:", 1)[-1]
            task = self.lip_sync_task_repository.get_task(target_id)
            if (
                task is None
                or task["role_id"] != role_id
                or task.get("final_deleted_at")
                or task.get("status") != "success"
                or not task.get("output_video_url")
            ):
                raise ValueError("成片不存在")
            self.file_cleanup_service.remove_paths([task.get("output_video_url")])
            return self.lip_sync_task_repository.soft_delete_final(target_id)
        raise ValueError("成片不存在")

    def batch_delete_final_videos(self, *, role_id: str, items: list[dict]):
        deleted_items: list[dict] = []
        failed_items: list[dict] = []
        for item in items:
            try:
                deleted_items.append(
                    self.delete_final_video(
                        item_id=str(item.get("id") or ""),
                        source_type=str(item.get("source_type") or ""),
                        role_id=role_id,
                    )
                )
            except ValueError:
                failed_items.append(item)
        return {
            "deleted_count": len(deleted_items),
            "failed_count": len(failed_items),
            "deleted_items": deleted_items,
            "failed_items": failed_items,
        }
