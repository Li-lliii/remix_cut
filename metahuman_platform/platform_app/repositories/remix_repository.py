import uuid

from platform_app.repositories.base import BaseRepository, now_iso, row_to_dict


class RemixSegmentRepository(BaseRepository):
    def replace_for_video(self, *, role_id: str, source_video_id: str, segments: list[dict]):
        created_at = now_iso()
        with self.connection() as connection:
            connection.execute(
                "DELETE FROM remix_segments WHERE source_video_id = ?",
                (source_video_id,),
            )
            for segment in segments:
                connection.execute(
                    """
                    INSERT INTO remix_segments (
                        id, role_id, source_video_id, segment_file_path,
                        start_sec, end_sec, duration_sec, asr_text, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        segment.get("segment_id") or str(uuid.uuid4()),
                        role_id,
                        source_video_id,
                        segment["segment_file_path"],
                        segment["start_sec"],
                        segment["end_sec"],
                        segment["duration_sec"],
                        segment["asr_text"],
                        created_at,
                    ),
                )
            connection.commit()
            rows = connection.execute(
                """
                SELECT * FROM remix_segments
                WHERE source_video_id = ?
                ORDER BY created_at ASC, start_sec ASC
                """,
                (source_video_id,),
            ).fetchall()
        return [row_to_dict(row) for row in rows]

    def list_by_video(self, source_video_id: str):
        with self.connection() as connection:
            rows = connection.execute(
                """
                SELECT * FROM remix_segments
                WHERE source_video_id = ?
                ORDER BY created_at ASC, start_sec ASC
                """,
                (source_video_id,),
            ).fetchall()
        return [row_to_dict(row) for row in rows]

    def delete_by_video(self, source_video_id: str):
        with self.connection() as connection:
            connection.execute(
                "DELETE FROM remix_segments WHERE source_video_id = ?",
                (source_video_id,),
            )
            connection.commit()


class RemixTaskRepository(BaseRepository):
    def create_task(
        self,
        *,
        role_id: str,
        source_video_id: str,
        task_batch_no: str | None = None,
        prompt_text: str,
        product_doc_url: str,
        target_count: int,
        is_max_mode: bool,
        aspect_mode: str,
        resolution: str,
        subtitle_enabled: bool,
        status: str,
    ):
        task_id = str(uuid.uuid4())
        created_at = now_iso()
        with self.connection() as connection:
            connection.execute(
                """
                INSERT INTO remix_tasks (
                    id, role_id, source_video_id, task_batch_no, prompt_text, product_doc_url,
                    target_count, is_max_mode, aspect_mode, resolution, subtitle_enabled, status, error_message,
                    running_count, success_count, failed_count, created_at, finished_at, deleted_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL, 0, 0, 0, ?, NULL, NULL)
                """,
                (
                    task_id,
                    role_id,
                    source_video_id,
                    task_batch_no or f"batch-{task_id[:8]}",
                    prompt_text,
                    product_doc_url,
                    target_count,
                    1 if is_max_mode else 0,
                    aspect_mode,
                    resolution,
                    1 if subtitle_enabled else 0,
                    status,
                    created_at,
                ),
            )
            connection.commit()
            row = connection.execute("SELECT * FROM remix_tasks WHERE id = ?", (task_id,)).fetchone()
        return row_to_dict(row)

    def get_task(self, task_id: str):
        with self.connection() as connection:
            row = connection.execute("SELECT * FROM remix_tasks WHERE id = ?", (task_id,)).fetchone()
        return row_to_dict(row)

    def list_tasks(self, *, include_deleted: bool = False):
        query = "SELECT * FROM remix_tasks"
        if not include_deleted:
            query += " WHERE deleted_at IS NULL"
        query += " ORDER BY created_at DESC"
        with self.connection() as connection:
            rows = connection.execute(query).fetchall()
        return [row_to_dict(row) for row in rows]

    def list_all_tasks(self):
        with self.connection() as connection:
            rows = connection.execute(
                "SELECT * FROM remix_tasks ORDER BY created_at DESC"
            ).fetchall()
        return [row_to_dict(row) for row in rows]

    def update_task_status(self, task_id: str, *, status: str, error_message: str | None = None):
        finished_at = now_iso() if status in {"success", "partial_success", "failed", "cancelled"} else None
        with self.connection() as connection:
            connection.execute(
                """
                UPDATE remix_tasks
                SET status = ?, error_message = COALESCE(?, error_message), finished_at = COALESCE(?, finished_at)
                WHERE id = ?
                """,
                (status, error_message, finished_at, task_id),
            )
            connection.commit()
            row = connection.execute("SELECT * FROM remix_tasks WHERE id = ?", (task_id,)).fetchone()
        return row_to_dict(row)

    def soft_delete(self, task_id: str):
        with self.connection() as connection:
            connection.execute(
                "UPDATE remix_tasks SET deleted_at = ? WHERE id = ?",
                (now_iso(), task_id),
            )
            connection.commit()
            row = connection.execute("SELECT * FROM remix_tasks WHERE id = ?", (task_id,)).fetchone()
        return row_to_dict(row)

    def create_task_item(self, *, remix_task_id: str, segment_id: str, status: str = "pending"):
        item_id = str(uuid.uuid4())
        created_at = now_iso()
        with self.connection() as connection:
            connection.execute(
                """
                INSERT INTO remix_task_items (
                    id, remix_task_id, segment_id, comfy_prompt_id, rewritten_text, tts_audio_path,
                    output_video_url, status, error_message, created_at, finished_at, final_deleted_at
                ) VALUES (?, ?, ?, NULL, NULL, NULL, NULL, ?, NULL, ?, NULL, NULL)
                """,
                (item_id, remix_task_id, segment_id, status, created_at),
            )
            connection.commit()
            row = connection.execute(
                "SELECT * FROM remix_task_items WHERE id = ?",
                (item_id,),
            ).fetchone()
        return row_to_dict(row)

    def create_items(self, remix_task_id: str, segment_ids: list[str], status: str = "pending"):
        return [
            self.create_task_item(remix_task_id=remix_task_id, segment_id=segment_id, status=status)
            for segment_id in segment_ids
        ]

    def update_task_item(
        self,
        item_id: str,
        *,
        status: str,
        comfy_prompt_id: str | None = None,
        rewritten_text: str | None = None,
        tts_audio_path: str | None = None,
        output_video_url: str | None = None,
        error_message: str | None = None,
    ):
        finished_at = now_iso() if status in {"success", "failed", "cancelled"} else None
        with self.connection() as connection:
            connection.execute(
                """
                UPDATE remix_task_items
                SET status = ?, comfy_prompt_id = ?, rewritten_text = ?, tts_audio_path = ?, output_video_url = ?,
                    error_message = ?, finished_at = ?
                WHERE id = ?
                """,
                (
                    status,
                    comfy_prompt_id,
                    rewritten_text,
                    tts_audio_path,
                    output_video_url,
                    error_message,
                    finished_at,
                    item_id,
                ),
            )
            connection.commit()
            row = connection.execute(
                "SELECT * FROM remix_task_items WHERE id = ?",
                (item_id,),
            ).fetchone()
        return row_to_dict(row)

    def update_item(
        self,
        item_id: str,
        *,
        status: str,
        comfy_prompt_id: str | None = None,
        rewritten_text: str | None = None,
        tts_audio_path: str | None = None,
        output_video_url: str | None = None,
        error_message: str | None = None,
    ):
        return self.update_task_item(
            item_id,
            status=status,
            comfy_prompt_id=comfy_prompt_id,
            rewritten_text=rewritten_text,
            tts_audio_path=tts_audio_path,
            output_video_url=output_video_url,
            error_message=error_message,
        )

    def update_counts(self, task_id: str):
        with self.connection() as connection:
            stats = connection.execute(
                """
                SELECT
                    SUM(CASE WHEN status IN ('pending', 'running', 'rewriting', 'tts_generating', 'video_generating') THEN 1 ELSE 0 END) AS running_count,
                    SUM(CASE WHEN status = 'success' THEN 1 ELSE 0 END) AS success_count,
                    SUM(CASE WHEN status = 'failed' THEN 1 ELSE 0 END) AS failed_count
                FROM remix_task_items
                WHERE remix_task_id = ?
                """,
                (task_id,),
            ).fetchone()
            connection.execute(
                """
                UPDATE remix_tasks
                SET running_count = ?, success_count = ?, failed_count = ?
                WHERE id = ?
                """,
                (
                    stats["running_count"] or 0,
                    stats["success_count"] or 0,
                    stats["failed_count"] or 0,
                    task_id,
                ),
            )
            connection.commit()
            row = connection.execute("SELECT * FROM remix_tasks WHERE id = ?", (task_id,)).fetchone()
        return row_to_dict(row)

    def refresh_counts(self, task_id: str):
        return self.update_counts(task_id)

    def list_items(self, remix_task_id: str):
        with self.connection() as connection:
            rows = connection.execute(
                """
                SELECT * FROM remix_task_items
                WHERE remix_task_id = ? AND final_deleted_at IS NULL
                ORDER BY created_at ASC
                """,
                (remix_task_id,),
            ).fetchall()
        return [row_to_dict(row) for row in rows]

    def get_item(self, item_id: str):
        with self.connection() as connection:
            row = connection.execute(
                "SELECT * FROM remix_task_items WHERE id = ?",
                (item_id,),
            ).fetchone()
        return row_to_dict(row)

    def soft_delete_item(self, item_id: str):
        with self.connection() as connection:
            connection.execute(
                "UPDATE remix_task_items SET final_deleted_at = ? WHERE id = ?",
                (now_iso(), item_id),
            )
            connection.commit()
            row = connection.execute(
                "SELECT * FROM remix_task_items WHERE id = ?",
                (item_id,),
            ).fetchone()
        return row_to_dict(row)
