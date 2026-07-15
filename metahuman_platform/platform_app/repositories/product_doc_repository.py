import uuid

from platform_app.repositories.base import BaseRepository, now_iso, row_to_dict


class ProductDocRepository(BaseRepository):
    def create(
        self,
        *,
        role_id: str,
        name: str,
        file_path: str,
        content: str,
    ):
        doc_id = str(uuid.uuid4())
        created_at = now_iso()
        with self.connection() as connection:
            connection.execute(
                """
                INSERT INTO role_product_docs (id, role_id, name, file_path, content, created_at, deleted_at)
                VALUES (?, ?, ?, ?, ?, ?, NULL)
                """,
                (doc_id, role_id, name, file_path, content, created_at),
            )
            connection.commit()
            row = connection.execute(
                "SELECT * FROM role_product_docs WHERE id = ?",
                (doc_id,),
            ).fetchone()
        return row_to_dict(row)

    def list_by_role(self, role_id: str):
        with self.connection() as connection:
            rows = connection.execute(
                """
                SELECT * FROM role_product_docs
                WHERE role_id = ? AND deleted_at IS NULL
                ORDER BY created_at DESC
                """,
                (role_id,),
            ).fetchall()
        return [row_to_dict(row) for row in rows]

    def get(self, doc_id: str):
        with self.connection() as connection:
            row = connection.execute(
                "SELECT * FROM role_product_docs WHERE id = ? AND deleted_at IS NULL",
                (doc_id,),
            ).fetchone()
        return row_to_dict(row)
