import uuid

from platform_app.repositories.base import BaseRepository, now_iso, row_to_dict


class PreprocessJobRepository(BaseRepository):
    def create(self, *, role_video_id: str, job_type: str, status: str = "pending", progress: int = 0):
        job_id = str(uuid.uuid4())
        started_at = now_iso()
        with self.connection() as connection:
            connection.execute(
                """
                INSERT INTO video_preprocess_jobs (
                    id, role_video_id, job_type, status, progress, error_message, started_at, finished_at, deleted_at
                ) VALUES (?, ?, ?, ?, ?, NULL, ?, NULL, NULL)
                """,
                (job_id, role_video_id, job_type, status, progress, started_at),
            )
            connection.commit()
            row = connection.execute(
                "SELECT * FROM video_preprocess_jobs WHERE id = ?",
                (job_id,),
            ).fetchone()
        return row_to_dict(row)

    def get(self, job_id: str):
        with self.connection() as connection:
            row = connection.execute(
                "SELECT * FROM video_preprocess_jobs WHERE id = ?",
                (job_id,),
            ).fetchone()
        return row_to_dict(row)

    def list_by_video(self, role_video_id: str):
        with self.connection() as connection:
            rows = connection.execute(
                """
                SELECT * FROM video_preprocess_jobs
                WHERE role_video_id = ? AND deleted_at IS NULL
                ORDER BY started_at DESC
                """,
                (role_video_id,),
            ).fetchall()
        return [row_to_dict(row) for row in rows]

    def soft_delete(self, job_id: str):
        with self.connection() as connection:
            connection.execute(
                "UPDATE video_preprocess_jobs SET deleted_at = ? WHERE id = ?",
                (now_iso(), job_id),
            )
            connection.commit()
            row = connection.execute(
                "SELECT * FROM video_preprocess_jobs WHERE id = ?",
                (job_id,),
            ).fetchone()
        return row_to_dict(row)

    def latest_by_video(self, role_video_id: str):
        jobs = self.list_by_video(role_video_id)
        return jobs[0] if jobs else None

    def update_status(
        self,
        job_id: str,
        *,
        status: str,
        progress: int | None = None,
        error_message: str | None = None,
    ):
        current = self.get(job_id)
        if current is None:
            return None
        next_progress = current["progress"] if progress is None else progress
        finished_at = now_iso() if status in {"success", "failed", "cancelled"} else None
        with self.connection() as connection:
            connection.execute(
                """
                UPDATE video_preprocess_jobs
                SET status = ?, progress = ?, error_message = ?, finished_at = ?
                WHERE id = ?
                """,
                (status, next_progress, error_message, finished_at, job_id),
            )
            connection.commit()
            row = connection.execute(
                "SELECT * FROM video_preprocess_jobs WHERE id = ?",
                (job_id,),
            ).fetchone()
        return row_to_dict(row)

    def update(
        self,
        job_id: str,
        *,
        status: str,
        progress: int | None = None,
        error_message: str | None = None,
    ):
        return self.update_status(
            job_id,
            status=status,
            progress=progress,
            error_message=error_message,
        )
