import json
import uuid

from platform_app.repositories.base import BaseRepository, now_iso, row_to_dict


class AsrRepository(BaseRepository):
    def upsert(self, *, role_video_id: str, full_text: str, segments: list[dict]):
        timestamp = now_iso()
        asr_id = str(uuid.uuid4())
        with self.connection() as connection:
            existing = connection.execute(
                "SELECT id FROM video_asr_results WHERE role_video_id = ?",
                (role_video_id,),
            ).fetchone()
            if existing:
                connection.execute(
                    """
                    UPDATE video_asr_results
                    SET full_text = ?,
                        segments_json = ?,
                        summary_text = '',
                        summary_status = 'pending',
                        summary_error_message = NULL,
                        summary_updated_at = NULL,
                        updated_at = ?
                    WHERE role_video_id = ?
                    """,
                    (full_text, json.dumps(segments, ensure_ascii=False), timestamp, role_video_id),
                )
            else:
                connection.execute(
                    """
                    INSERT INTO video_asr_results (
                        id, role_video_id, full_text, segments_json, summary_text, summary_status,
                        summary_error_message, summary_updated_at, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        asr_id,
                        role_video_id,
                        full_text,
                        json.dumps(segments, ensure_ascii=False),
                        "",
                        "pending",
                        None,
                        None,
                        timestamp,
                        timestamp,
                    ),
                )
            connection.execute(
                """
                UPDATE role_videos
                SET asr_status = 'success', asr_error_message = NULL
                WHERE id = ?
                """,
                (role_video_id,),
            )
            connection.commit()
        return self.get_by_video(role_video_id)

    def update_summary(self, *, role_video_id: str, summary_text: str):
        timestamp = now_iso()
        with self.connection() as connection:
            connection.execute(
                """
                UPDATE video_asr_results
                SET summary_text = ?,
                    summary_status = 'success',
                    summary_error_message = NULL,
                    summary_updated_at = ?
                WHERE role_video_id = ?
                """,
                (summary_text, timestamp, role_video_id),
            )
            connection.commit()
        return self.get_by_video(role_video_id)

    def mark_summary_failed(self, *, role_video_id: str, error_message: str):
        timestamp = now_iso()
        with self.connection() as connection:
            connection.execute(
                """
                UPDATE video_asr_results
                SET summary_status = 'failed',
                    summary_error_message = ?,
                    summary_updated_at = ?
                WHERE role_video_id = ?
                """,
                (error_message, timestamp, role_video_id),
            )
            connection.commit()
        return self.get_by_video(role_video_id)

    def get_by_video(self, role_video_id: str):
        with self.connection() as connection:
            row = connection.execute(
                "SELECT * FROM video_asr_results WHERE role_video_id = ?",
                (role_video_id,),
            ).fetchone()
        if row is None:
            return None
        data = dict(row)
        data["segments"] = json.loads(data.pop("segments_json"))
        return data
