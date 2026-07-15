import uuid

from platform_app.repositories.base import BaseRepository, now_iso, row_to_dict


class LipSyncProjectRepository(BaseRepository):
    def create_project(
        self,
        *,
        role_id: str,
        base_video_id: str,
        prompt_text: str,
        product_doc_url: str,
        status: str,
    ):
        project_id = str(uuid.uuid4())
        created_at = now_iso()
        with self.connection() as connection:
            connection.execute(
                """
                INSERT INTO lip_sync_projects (
                    id, role_id, base_video_id, prompt_text, product_doc_url, status, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    project_id,
                    role_id,
                    base_video_id,
                    prompt_text,
                    product_doc_url,
                    status,
                    created_at,
                ),
            )
            connection.commit()
            row = connection.execute(
                "SELECT * FROM lip_sync_projects WHERE id = ?",
                (project_id,),
            ).fetchone()
        return row_to_dict(row)

    def get_project(self, project_id: str):
        with self.connection() as connection:
            row = connection.execute(
                "SELECT * FROM lip_sync_projects WHERE id = ?",
                (project_id,),
            ).fetchone()
        return row_to_dict(row)

    def update_status(self, project_id: str, *, status: str):
        with self.connection() as connection:
            connection.execute(
                "UPDATE lip_sync_projects SET status = ? WHERE id = ?",
                (status, project_id),
            )
            connection.commit()
            row = connection.execute(
                "SELECT * FROM lip_sync_projects WHERE id = ?",
                (project_id,),
            ).fetchone()
        return row_to_dict(row)

    def list_projects(self):
        with self.connection() as connection:
            rows = connection.execute(
                "SELECT * FROM lip_sync_projects ORDER BY created_at DESC"
            ).fetchall()
        return [row_to_dict(row) for row in rows]


class ScriptCandidateRepository(BaseRepository):
    def replace_candidates(self, *, project_id: str, candidates: list[dict]):
        created_at = now_iso()
        with self.connection() as connection:
            connection.execute(
                "DELETE FROM script_candidates WHERE project_id = ?",
                (project_id,),
            )
            for index, candidate in enumerate(candidates, start=1):
                connection.execute(
                    """
                    INSERT INTO script_candidates (
                        id, project_id, content, char_count, estimated_tts_duration_sec,
                        version_no, is_selected, edited_content, is_edited, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, 0, NULL, 0, ?)
                    """,
                    (
                        str(uuid.uuid4()),
                        project_id,
                        candidate["content"],
                        candidate["char_count"],
                        candidate["estimated_tts_duration_sec"],
                        index,
                        created_at,
                    ),
                )
            connection.commit()
            rows = connection.execute(
                """
                SELECT * FROM script_candidates
                WHERE project_id = ?
                ORDER BY version_no ASC, created_at ASC
                """,
                (project_id,),
            ).fetchall()
        return [row_to_dict(row) for row in rows]

    def list_candidates(self, project_id: str):
        with self.connection() as connection:
            rows = connection.execute(
                """
                SELECT * FROM script_candidates
                WHERE project_id = ?
                ORDER BY version_no ASC, created_at ASC
                """,
                (project_id,),
            ).fetchall()
        return [row_to_dict(row) for row in rows]

    def get_candidate(self, candidate_id: str):
        with self.connection() as connection:
            row = connection.execute(
                "SELECT * FROM script_candidates WHERE id = ?",
                (candidate_id,),
            ).fetchone()
        return row_to_dict(row)

    def update_candidate(
        self,
        candidate_id: str,
        *,
        is_selected: bool | None = None,
        edited_content: str | None = None,
        is_edited: bool | None = None,
        content: str | None = None,
        char_count: int | None = None,
        estimated_tts_duration_sec: float | None = None,
    ):
        with self.connection() as connection:
            if is_selected is not None and is_selected:
                project_row = connection.execute(
                    "SELECT project_id FROM script_candidates WHERE id = ?",
                    (candidate_id,),
                ).fetchone()
                if project_row is not None:
                    connection.execute(
                        "UPDATE script_candidates SET is_selected = 0 WHERE project_id = ?",
                        (project_row["project_id"],),
                    )
            connection.execute(
                """
                UPDATE script_candidates
                SET is_selected = COALESCE(?, is_selected),
                    content = COALESCE(?, content),
                    char_count = COALESCE(?, char_count),
                    estimated_tts_duration_sec = COALESCE(?, estimated_tts_duration_sec),
                    edited_content = COALESCE(?, edited_content),
                    is_edited = COALESCE(?, is_edited)
                WHERE id = ?
                """,
                (
                    None if is_selected is None else (1 if is_selected else 0),
                    content,
                    char_count,
                    estimated_tts_duration_sec,
                    edited_content,
                    None if is_edited is None else (1 if is_edited else 0),
                    candidate_id,
                ),
            )
            connection.commit()
            row = connection.execute(
                "SELECT * FROM script_candidates WHERE id = ?",
                (candidate_id,),
            ).fetchone()
        return row_to_dict(row)


class LipSyncTaskRepository(BaseRepository):
    def create_task(
        self,
        *,
        project_id: str,
        role_id: str,
        base_video_id: str,
        selected_script_id: str,
        final_script_text: str,
        aspect_mode: str,
        resolution: str,
        subtitle_enabled: bool,
        status: str,
        video_job_id: str | None,
    ):
        task_id = str(uuid.uuid4())
        created_at = now_iso()
        with self.connection() as connection:
            connection.execute(
                """
                INSERT INTO lip_sync_tasks (
                    id, project_id, role_id, base_video_id, selected_script_id,
                    final_script_text, video_job_id, aspect_mode, resolution, subtitle_enabled,
                    status, tts_audio_path, output_video_url, error_message, created_at, finished_at,
                    deleted_at, final_deleted_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL, NULL, NULL, ?, NULL, NULL, NULL)
                """,
                (
                    task_id,
                    project_id,
                    role_id,
                    base_video_id,
                    selected_script_id,
                    final_script_text,
                    video_job_id,
                    aspect_mode,
                    resolution,
                    1 if subtitle_enabled else 0,
                    status,
                    created_at,
                ),
            )
            connection.commit()
            row = connection.execute(
                "SELECT * FROM lip_sync_tasks WHERE id = ?",
                (task_id,),
            ).fetchone()
        return row_to_dict(row)

    def get_task(self, task_id: str):
        with self.connection() as connection:
            row = connection.execute(
                "SELECT * FROM lip_sync_tasks WHERE id = ?",
                (task_id,),
            ).fetchone()
        return row_to_dict(row)

    def list_by_statuses(self, statuses: list[str], *, include_deleted: bool = False):
        if not statuses:
            return []
        placeholders = ", ".join("?" for _ in statuses)
        query = f"SELECT * FROM lip_sync_tasks WHERE status IN ({placeholders})"
        if not include_deleted:
            query += " AND deleted_at IS NULL"
        query += " ORDER BY created_at ASC, id ASC"
        with self.connection() as connection:
            rows = connection.execute(query, tuple(statuses)).fetchall()
        return [row_to_dict(row) for row in rows]

    def get_active_task(self):
        tasks = self.list_by_statuses(["starting", "video_generating"])
        return tasks[0] if tasks else None

    def get_next_waiting_task(self):
        tasks = self.list_by_statuses(["pending", "queued"])
        return tasks[0] if tasks else None

    def list_tasks(self, *, include_deleted: bool = False):
        query = "SELECT * FROM lip_sync_tasks"
        if not include_deleted:
            query += " WHERE deleted_at IS NULL"
        query += " ORDER BY created_at DESC"
        with self.connection() as connection:
            rows = connection.execute(query).fetchall()
        return [row_to_dict(row) for row in rows]

    def list_all_tasks(self):
        with self.connection() as connection:
            rows = connection.execute(
                "SELECT * FROM lip_sync_tasks ORDER BY created_at DESC"
            ).fetchall()
        return [row_to_dict(row) for row in rows]

    def update_task(
        self,
        task_id: str,
        *,
        status: str,
        final_script_text: str | None = None,
        video_job_id: str | None = None,
        tts_audio_path: str | None = None,
        output_video_url: str | None = None,
        error_message: str | None = None,
    ):
        finished_at = now_iso() if status in {"success", "failed", "cancelled"} else None
        with self.connection() as connection:
            connection.execute(
                """
                UPDATE lip_sync_tasks
                SET status = ?,
                    final_script_text = COALESCE(?, final_script_text),
                    video_job_id = COALESCE(?, video_job_id),
                    tts_audio_path = COALESCE(?, tts_audio_path),
                    output_video_url = COALESCE(?, output_video_url),
                    error_message = COALESCE(?, error_message),
                    finished_at = COALESCE(?, finished_at)
                WHERE id = ?
                """,
                (
                    status,
                    final_script_text,
                    video_job_id,
                    tts_audio_path,
                    output_video_url,
                    error_message,
                    finished_at,
                    task_id,
                ),
            )
            connection.commit()
            row = connection.execute(
                "SELECT * FROM lip_sync_tasks WHERE id = ?",
                (task_id,),
            ).fetchone()
        return row_to_dict(row)

    def soft_delete(self, task_id: str):
        with self.connection() as connection:
            connection.execute(
                "UPDATE lip_sync_tasks SET deleted_at = ? WHERE id = ?",
                (now_iso(), task_id),
            )
            connection.commit()
            row = connection.execute(
                "SELECT * FROM lip_sync_tasks WHERE id = ?",
                (task_id,),
            ).fetchone()
        return row_to_dict(row)

    def soft_delete_final(self, task_id: str):
        with self.connection() as connection:
            connection.execute(
                "UPDATE lip_sync_tasks SET final_deleted_at = ? WHERE id = ?",
                (now_iso(), task_id),
            )
            connection.commit()
            row = connection.execute(
                "SELECT * FROM lip_sync_tasks WHERE id = ?",
                (task_id,),
            ).fetchone()
        return row_to_dict(row)
