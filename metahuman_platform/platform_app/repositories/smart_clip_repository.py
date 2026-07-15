import uuid

from platform_app.repositories.base import BaseRepository, now_iso, row_to_dict


def _smart_clip_row_to_dict(row):
    data = row_to_dict(row)
    if data is None:
        return None
    if "keep_flag" in data:
        data["keep_flag"] = bool(data["keep_flag"])
    return data


class SmartClipRepository(BaseRepository):
    def create_project(
        self,
        *,
        role_id: str,
        source_video_id: str,
        source_video_title: str,
        status: str,
        stage: str,
    ):
        project_id = str(uuid.uuid4())
        timestamp = now_iso()
        with self.connection() as connection:
            connection.execute(
                """
                INSERT INTO smart_clip_projects (
                    id, role_id, source_video_id, source_video_title, status, stage,
                    total_asr_segments, kept_sales_segments, candidate_clip_count,
                    export_total_count, export_completed_count, export_current_index,
                    error_message, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, 0, 0, 0, 0, 0, 0, NULL, ?, ?)
                """,
                (project_id, role_id, source_video_id, source_video_title, status, stage, timestamp, timestamp),
            )
            connection.commit()
            row = connection.execute(
                "SELECT * FROM smart_clip_projects WHERE id = ?",
                (project_id,),
            ).fetchone()
        return _smart_clip_row_to_dict(row)

    def get_project(self, project_id: str):
        with self.connection() as connection:
            row = connection.execute(
                "SELECT * FROM smart_clip_projects WHERE id = ?",
                (project_id,),
            ).fetchone()
        return _smart_clip_row_to_dict(row)

    def list_projects_by_role(self, role_id: str):
        with self.connection() as connection:
            rows = connection.execute(
                """
                SELECT * FROM smart_clip_projects
                WHERE role_id = ?
                ORDER BY created_at DESC
                """,
                (role_id,),
            ).fetchall()
        return [_smart_clip_row_to_dict(row) for row in rows]

    def update_project_status(self, project_id: str, *, status: str, stage: str | None = None, error_message: str | None = None):
        current = self.get_project(project_id)
        if current is None:
            return None
        next_stage = current["stage"] if stage is None else stage
        with self.connection() as connection:
            connection.execute(
                """
                UPDATE smart_clip_projects
                SET status = ?,
                    stage = ?,
                    error_message = ?,
                    updated_at = ?
                WHERE id = ?
                """,
                (status, next_stage, error_message, now_iso(), project_id),
            )
            connection.commit()
            row = connection.execute(
                "SELECT * FROM smart_clip_projects WHERE id = ?",
                (project_id,),
            ).fetchone()
        return _smart_clip_row_to_dict(row)

    def update_project_progress(
        self,
        project_id: str,
        *,
        stage: str | None = None,
        total_asr_segments: int | None = None,
        kept_sales_segments: int | None = None,
        candidate_clip_count: int | None = None,
        export_total_count: int | None = None,
        export_completed_count: int | None = None,
        export_current_index: int | None = None,
    ):
        current = self.get_project(project_id)
        if current is None:
            return None
        with self.connection() as connection:
            connection.execute(
                """
                UPDATE smart_clip_projects
                SET stage = ?,
                    total_asr_segments = ?,
                    kept_sales_segments = ?,
                    candidate_clip_count = ?,
                    export_total_count = ?,
                    export_completed_count = ?,
                    export_current_index = ?,
                    updated_at = ?
                WHERE id = ?
                """,
                (
                    current["stage"] if stage is None else stage,
                    current["total_asr_segments"] if total_asr_segments is None else total_asr_segments,
                    current["kept_sales_segments"] if kept_sales_segments is None else kept_sales_segments,
                    current["candidate_clip_count"] if candidate_clip_count is None else candidate_clip_count,
                    current["export_total_count"] if export_total_count is None else export_total_count,
                    current["export_completed_count"] if export_completed_count is None else export_completed_count,
                    current["export_current_index"] if export_current_index is None else export_current_index,
                    now_iso(),
                    project_id,
                ),
            )
            connection.commit()
            row = connection.execute(
                "SELECT * FROM smart_clip_projects WHERE id = ?",
                (project_id,),
            ).fetchone()
        return _smart_clip_row_to_dict(row)

    def replace_segments(self, *, project_id: str, source_video_id: str, segments: list[dict]):
        created_at = now_iso()
        with self.connection() as connection:
            connection.execute("DELETE FROM smart_clip_segments WHERE project_id = ?", (project_id,))
            for segment in segments:
                connection.execute(
                    """
                    INSERT INTO smart_clip_segments (
                        id, project_id, source_video_id, start_sec, end_sec, duration_sec,
                        asr_text, classification, keep_flag, reason, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        segment.get("id") or str(uuid.uuid4()),
                        project_id,
                        source_video_id,
                        segment["start_sec"],
                        segment["end_sec"],
                        segment["duration_sec"],
                        segment["asr_text"],
                        segment["classification"],
                        1 if segment.get("keep_flag", True) else 0,
                        segment.get("reason"),
                        created_at,
                    ),
                )
            connection.commit()
            rows = connection.execute(
                """
                SELECT * FROM smart_clip_segments
                WHERE project_id = ?
                ORDER BY start_sec ASC, created_at ASC
                """,
                (project_id,),
            ).fetchall()
        return [_smart_clip_row_to_dict(row) for row in rows]

    def list_segments(self, project_id: str):
        with self.connection() as connection:
            rows = connection.execute(
                """
                SELECT * FROM smart_clip_segments
                WHERE project_id = ?
                ORDER BY start_sec ASC, created_at ASC
                """,
                (project_id,),
            ).fetchall()
        return [_smart_clip_row_to_dict(row) for row in rows]

    def replace_candidates(self, *, project_id: str, candidates: list[dict]):
        timestamp = now_iso()
        with self.connection() as connection:
            connection.execute("DELETE FROM smart_clip_candidates WHERE project_id = ?", (project_id,))
            for candidate in candidates:
                connection.execute(
                    """
                    INSERT INTO smart_clip_candidates (
                        id, project_id, clip_index, title, duration_sec,
                        segment_refs_json, source_time_ranges_json, preview_text,
                        status, output_video_path, error_message, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, NULL, NULL, ?, ?)
                    """,
                    (
                        candidate.get("id") or str(uuid.uuid4()),
                        project_id,
                        candidate["clip_index"],
                        candidate["title"],
                        candidate["duration_sec"],
                        candidate["segment_refs_json"],
                        candidate["source_time_ranges_json"],
                        candidate.get("preview_text", ""),
                        candidate["status"],
                        timestamp,
                        timestamp,
                    ),
                )
            connection.commit()
            rows = connection.execute(
                """
                SELECT * FROM smart_clip_candidates
                WHERE project_id = ?
                ORDER BY clip_index ASC, created_at ASC
                """,
                (project_id,),
            ).fetchall()
        return [_smart_clip_row_to_dict(row) for row in rows]

    def list_candidates(self, project_id: str, include_deleted: bool = False):
        query = """
            SELECT * FROM smart_clip_candidates
            WHERE project_id = ?
        """
        params = [project_id]
        if not include_deleted:
            query += " AND status != 'deleted'"
        query += " ORDER BY clip_index ASC, created_at ASC"
        with self.connection() as connection:
            rows = connection.execute(query, params).fetchall()
        return [_smart_clip_row_to_dict(row) for row in rows]

    def get_candidate(self, candidate_id: str):
        with self.connection() as connection:
            row = connection.execute(
                "SELECT * FROM smart_clip_candidates WHERE id = ?",
                (candidate_id,),
            ).fetchone()
        return _smart_clip_row_to_dict(row)

    def soft_delete_candidate(self, candidate_id: str):
        with self.connection() as connection:
            connection.execute(
                """
                UPDATE smart_clip_candidates
                SET status = 'deleted',
                    updated_at = ?
                WHERE id = ?
                """,
                (now_iso(), candidate_id),
            )
            connection.commit()
            row = connection.execute(
                "SELECT * FROM smart_clip_candidates WHERE id = ?",
                (candidate_id,),
            ).fetchone()
        return _smart_clip_row_to_dict(row)

    def mark_candidate_exporting(self, candidate_id: str):
        return self._update_candidate_status(candidate_id, status="exporting")

    def set_candidate_preview_path(self, candidate_id: str, *, output_video_path: str):
        return self._update_candidate_status(candidate_id, status="active", output_video_path=output_video_path)

    def mark_candidate_exported(self, candidate_id: str, *, output_video_path: str):
        return self._update_candidate_status(candidate_id, status="exported", output_video_path=output_video_path)

    def mark_candidate_failed(self, candidate_id: str, *, error_message: str):
        return self._update_candidate_status(candidate_id, status="failed", error_message=error_message)

    def _update_candidate_status(
        self,
        candidate_id: str,
        *,
        status: str,
        output_video_path: str | None = None,
        error_message: str | None = None,
    ):
        current = self.get_candidate(candidate_id)
        if current is None:
            return None
        next_output_video_path = current["output_video_path"]
        next_error_message = current["error_message"]
        if status == "failed":
            next_output_video_path = None
            next_error_message = error_message
        elif status == "exporting":
            next_output_video_path = None
            next_error_message = None
        elif status == "exported":
            next_output_video_path = output_video_path
            next_error_message = None
        else:
            if output_video_path is not None:
                next_output_video_path = output_video_path
            if error_message is not None:
                next_error_message = error_message
        with self.connection() as connection:
            connection.execute(
                """
                UPDATE smart_clip_candidates
                SET status = ?,
                    output_video_path = ?,
                    error_message = ?,
                    updated_at = ?
                WHERE id = ?
                """,
                (
                    status,
                    next_output_video_path,
                    next_error_message,
                    now_iso(),
                    candidate_id,
                ),
            )
            connection.commit()
            row = connection.execute(
                "SELECT * FROM smart_clip_candidates WHERE id = ?",
                (candidate_id,),
            ).fetchone()
        return _smart_clip_row_to_dict(row)
