import json
import uuid

from platform_app.repositories.base import BaseRepository, now_iso, row_to_dict


class RoleRepository(BaseRepository):
    def create(self, *, name: str, description: str, tags: list[str], avatar_url: str):
        role_id = str(uuid.uuid4())
        timestamp = now_iso()
        with self.connection() as connection:
            connection.execute(
                """
                INSERT INTO roles (id, name, avatar_url, description, tags, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    role_id,
                    name,
                    avatar_url,
                    description,
                    json.dumps(tags, ensure_ascii=False),
                    timestamp,
                    timestamp,
                ),
            )
            connection.commit()
            row = connection.execute("SELECT * FROM roles WHERE id = ?", (role_id,)).fetchone()
        return row_to_dict(row)

    def list(self, *, search: str | None = None):
        params = []
        query = """
        SELECT
            roles.*,
            COUNT(role_videos.id) AS video_count,
            0 AS pending_review_count
        FROM roles
        LEFT JOIN role_videos
            ON role_videos.role_id = roles.id
            AND role_videos.deleted_at IS NULL
        """
        if search:
            query += " WHERE roles.name LIKE ?"
            params.append(f"%{search}%")
        query += " GROUP BY roles.id ORDER BY roles.updated_at DESC"
        with self.connection() as connection:
            rows = connection.execute(query, params).fetchall()
        return [row_to_dict(row) for row in rows]

    def get(self, role_id: str):
        with self.connection() as connection:
            row = connection.execute(
                """
                SELECT
                    roles.*,
                    COUNT(role_videos.id) AS video_count,
                    0 AS pending_review_count
                FROM roles
                LEFT JOIN role_videos
                    ON role_videos.role_id = roles.id
                    AND role_videos.deleted_at IS NULL
                WHERE roles.id = ?
                GROUP BY roles.id
                """,
                (role_id,),
            ).fetchone()
        return row_to_dict(row)

    def update_avatar(self, role_id: str, avatar_url: str):
        timestamp = now_iso()
        with self.connection() as connection:
            connection.execute(
                """
                UPDATE roles
                SET avatar_url = ?, updated_at = ?
                WHERE id = ?
                """,
                (avatar_url, timestamp, role_id),
            )
            connection.commit()
            row = connection.execute(
                """
                SELECT
                    roles.*,
                    COUNT(role_videos.id) AS video_count,
                    0 AS pending_review_count
                FROM roles
                LEFT JOIN role_videos
                    ON role_videos.role_id = roles.id
                    AND role_videos.deleted_at IS NULL
                WHERE roles.id = ?
                GROUP BY roles.id
                """,
                (role_id,),
            ).fetchone()
        return row_to_dict(row)
