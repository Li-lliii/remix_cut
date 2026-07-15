from pathlib import Path

from platform_app.services.file_cleanup_service import FileCleanupService
from platform_app.db import connect


class RoleDeletionService:
    def __init__(
        self,
        *,
        db_path: Path,
        uploads_dir: Path,
        temp_dir: Path,
        generated_dir: Path,
    ):
        self.db_path = Path(db_path)
        self.uploads_dir = Path(uploads_dir)
        self.temp_dir = Path(temp_dir)
        self.generated_dir = Path(generated_dir)
        self.file_cleanup_service = FileCleanupService()

    def _build_in_clause(self, values: list[str]):
        if not values:
            return None, []
        return ",".join(["?"] * len(values)), list(values)

    def delete_role(self, role_id: str):
        file_paths: set[str] = set()
        dir_paths: set[str] = set()
        with connect(self.db_path) as connection:
            role = connection.execute("SELECT * FROM roles WHERE id = ?", (role_id,)).fetchone()
            if role is None:
                raise ValueError("角色不存在")

            role_dir = self.uploads_dir / "roles" / role_id
            dir_paths.add(str(role_dir))

            video_rows = connection.execute(
                "SELECT id, file_path, thumbnail_url FROM role_videos WHERE role_id = ?",
                (role_id,),
            ).fetchall()
            video_ids = [str(row["id"]) for row in video_rows]
            for row in video_rows:
                file_paths.add(str(row["file_path"] or ""))
                file_paths.add(str(row["thumbnail_url"] or ""))

            product_doc_rows = connection.execute(
                "SELECT file_path FROM role_product_docs WHERE role_id = ?",
                (role_id,),
            ).fetchall()
            for row in product_doc_rows:
                file_paths.add(str(row["file_path"] or ""))

            smart_clip_rows = connection.execute(
                "SELECT id FROM smart_clip_projects WHERE role_id = ?",
                (role_id,),
            ).fetchall()
            smart_clip_project_ids = [str(row["id"]) for row in smart_clip_rows]
            for project_id in smart_clip_project_ids:
                dir_paths.add(str(self.generated_dir / "smart_clips" / project_id))
                dir_paths.add(str(self.temp_dir / "smart_clips" / project_id))

            smart_candidate_placeholder, smart_candidate_params = self._build_in_clause(smart_clip_project_ids)
            if smart_candidate_placeholder:
                smart_clip_candidate_rows = connection.execute(
                    f"SELECT output_video_path FROM smart_clip_candidates WHERE project_id IN ({smart_candidate_placeholder})",
                    smart_candidate_params,
                ).fetchall()
                for row in smart_clip_candidate_rows:
                    file_paths.add(str(row["output_video_path"] or ""))

            remix_segment_rows = connection.execute(
                "SELECT segment_file_path FROM remix_segments WHERE role_id = ?",
                (role_id,),
            ).fetchall()
            for row in remix_segment_rows:
                file_paths.add(str(row["segment_file_path"] or ""))

            remix_task_rows = connection.execute(
                "SELECT id FROM remix_tasks WHERE role_id = ?",
                (role_id,),
            ).fetchall()
            remix_task_ids = [str(row["id"]) for row in remix_task_rows]
            remix_task_placeholder, remix_task_params = self._build_in_clause(remix_task_ids)
            if remix_task_placeholder:
                remix_item_rows = connection.execute(
                    f"""
                    SELECT tts_audio_path, output_video_url
                    FROM remix_task_items
                    WHERE remix_task_id IN ({remix_task_placeholder})
                    """,
                    remix_task_params,
                ).fetchall()
                for row in remix_item_rows:
                    file_paths.add(str(row["tts_audio_path"] or ""))
                    file_paths.add(str(row["output_video_url"] or ""))

            lip_sync_project_rows = connection.execute(
                "SELECT id FROM lip_sync_projects WHERE role_id = ?",
                (role_id,),
            ).fetchall()
            lip_sync_project_ids = [str(row["id"]) for row in lip_sync_project_rows]
            lip_sync_task_rows = connection.execute(
                "SELECT id, tts_audio_path, output_video_url FROM lip_sync_tasks WHERE role_id = ?",
                (role_id,),
            ).fetchall()
            lip_sync_task_ids = []
            for row in lip_sync_task_rows:
                lip_sync_task_ids.append(str(row["id"]))
                file_paths.add(str(row["tts_audio_path"] or ""))
                file_paths.add(str(row["output_video_url"] or ""))

            review_source_ids = remix_task_ids + lip_sync_task_ids
            review_placeholder, review_params = self._build_in_clause(review_source_ids)
            if review_placeholder:
                connection.execute(
                    f"DELETE FROM review_records WHERE source_task_id IN ({review_placeholder})",
                    review_params,
                )

            if remix_task_placeholder:
                connection.execute(
                    f"DELETE FROM remix_task_items WHERE remix_task_id IN ({remix_task_placeholder})",
                    remix_task_params,
                )
            connection.execute("DELETE FROM remix_tasks WHERE role_id = ?", (role_id,))
            connection.execute("DELETE FROM remix_segments WHERE role_id = ?", (role_id,))

            lip_sync_project_placeholder, lip_sync_project_params = self._build_in_clause(lip_sync_project_ids)
            if lip_sync_project_placeholder:
                connection.execute(
                    f"DELETE FROM script_candidates WHERE project_id IN ({lip_sync_project_placeholder})",
                    lip_sync_project_params,
                )
            connection.execute("DELETE FROM lip_sync_tasks WHERE role_id = ?", (role_id,))
            connection.execute("DELETE FROM lip_sync_projects WHERE role_id = ?", (role_id,))

            if smart_candidate_placeholder:
                connection.execute(
                    f"DELETE FROM smart_clip_candidates WHERE project_id IN ({smart_candidate_placeholder})",
                    smart_candidate_params,
                )
                connection.execute(
                    f"DELETE FROM smart_clip_segments WHERE project_id IN ({smart_candidate_placeholder})",
                    smart_candidate_params,
                )
            connection.execute("DELETE FROM smart_clip_projects WHERE role_id = ?", (role_id,))

            video_placeholder, video_params = self._build_in_clause(video_ids)
            if video_placeholder:
                connection.execute(
                    f"DELETE FROM video_preprocess_jobs WHERE role_video_id IN ({video_placeholder})",
                    video_params,
                )
                connection.execute(
                    f"DELETE FROM video_asr_results WHERE role_video_id IN ({video_placeholder})",
                    video_params,
                )
            connection.execute("DELETE FROM role_product_docs WHERE role_id = ?", (role_id,))
            connection.execute("DELETE FROM role_videos WHERE role_id = ?", (role_id,))
            connection.execute("DELETE FROM roles WHERE id = ?", (role_id,))
            connection.commit()

        cleanup_targets = [path for path in sorted(file_paths | dir_paths) if str(path).strip()]
        self.file_cleanup_service.remove_paths(cleanup_targets)
        return {"success": True}
