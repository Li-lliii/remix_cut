import uuid

from platform_app.repositories.base import BaseRepository, row_to_dict


class ReviewRecordRepository(BaseRepository):
    def create(
        self,
        *,
        source_type: str,
        source_task_id: str,
        status: str,
        review_note: str = "",
        reviewed_at: str | None = None,
    ):
        review_id = str(uuid.uuid4())
        with self.connection() as connection:
            connection.execute(
                """
                INSERT INTO review_records (
                    id, source_type, source_task_id, status, review_note, reviewed_at
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (review_id, source_type, source_task_id, status, review_note, reviewed_at),
            )
            connection.commit()
            row = connection.execute(
                "SELECT * FROM review_records WHERE id = ?",
                (review_id,),
            ).fetchone()
        return row_to_dict(row)

    def create_pending(self, *, source_type: str, source_task_id: str):
        return self.create(
            source_type=source_type,
            source_task_id=source_task_id,
            status="pending_review",
            review_note="",
        )

    def list_pending(self):
        with self.connection() as connection:
            rows = connection.execute(
                """
                SELECT * FROM review_records
                WHERE status = 'pending_review'
                ORDER BY id DESC
                """
            ).fetchall()
        return [row_to_dict(row) for row in rows]
