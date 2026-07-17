import os
import uuid

from platform_app.repositories.base import BaseRepository, now_iso, row_to_dict


class VideoRepository(BaseRepository):
    def create(
        self,
        *,
        role_id: str,
        material_asset_id: str = "",
        title: str,
        file_path: str,
        thumbnail_url: str,
        duration_sec: float,
        aspect_ratio: str,
        video_id: str | None = None,
    ):
        video_id = video_id or str(uuid.uuid4())
        timestamp = now_iso()
        with self.connection() as connection:
            connection.execute(
                """
                INSERT INTO role_videos (
                    id, role_id, material_asset_id, title, file_path, thumbnail_url, duration_sec, aspect_ratio,
                    is_pinned, uploaded_at, deleted_at, asr_status, asr_error_message
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 0, ?, NULL, 'pending', NULL)
                """,
                (
                    video_id,
                    role_id,
                    material_asset_id,
                    title,
                    file_path,
                    thumbnail_url,
                    duration_sec,
                    aspect_ratio,
                    timestamp,
                ),
            )
            connection.commit()
            row = connection.execute(
                "SELECT * FROM role_videos WHERE id = ?", (video_id,)
            ).fetchone()
        return row_to_dict(row)

    def get(self, video_id: str, *, include_deleted: bool = False):
        query = "SELECT * FROM role_videos WHERE id = ?"
        params = [video_id]
        if not include_deleted:
            query += " AND deleted_at IS NULL"
        with self.connection() as connection:
            row = connection.execute(query, params).fetchone()
        return row_to_dict(row)

    def get_by_file_path(self, file_path: str, *, include_deleted: bool = False):
        query = "SELECT * FROM role_videos WHERE file_path = ?"
        params = [file_path]
        if not include_deleted:
            query += " AND deleted_at IS NULL"
        with self.connection() as connection:
            row = connection.execute(query, params).fetchone()
        return row_to_dict(row)

    def list_by_role(self, role_id: str):
        with self.connection() as connection:
            rows = connection.execute(
                """
                SELECT * FROM role_videos
                WHERE role_id = ? AND deleted_at IS NULL
                ORDER BY is_pinned DESC, uploaded_at DESC
                """,
                (role_id,),
            ).fetchall()
        return [row_to_dict(row) for row in rows]

    def list_all(self):
        with self.connection() as connection:
            rows = connection.execute(
                """
                SELECT * FROM role_videos
                WHERE deleted_at IS NULL
                ORDER BY uploaded_at DESC
                """
            ).fetchall()
        return [row_to_dict(row) for row in rows]

    def set_pinned(self, video_id: str, is_pinned: bool):
        with self.connection() as connection:
            connection.execute(
                "UPDATE role_videos SET is_pinned = ? WHERE id = ?",
                (1 if is_pinned else 0, video_id),
            )
            connection.commit()
            row = connection.execute(
                "SELECT * FROM role_videos WHERE id = ?", (video_id,)
            ).fetchone()
        return row_to_dict(row)

    def soft_delete(self, video_id: str):
        with self.connection() as connection:
            connection.execute(
                "UPDATE role_videos SET deleted_at = ? WHERE id = ?",
                (now_iso(), video_id),
            )
            connection.commit()

    def update_asr_status(self, video_id: str, status: str, error_message: str | None = None):
        with self.connection() as connection:
            connection.execute(
                """
                UPDATE role_videos
                SET asr_status = ?, asr_error_message = ?
                WHERE id = ?
                """,
                (status, error_message, video_id),
            )
            connection.commit()
            row = connection.execute(
                "SELECT * FROM role_videos WHERE id = ?", (video_id,)
            ).fetchone()
        return row_to_dict(row)

    def relative_stream_name(self, video_id: str) -> str | None:
        video = self.get(video_id)
        if not video:
            return None
        return os.path.basename(video["file_path"])
