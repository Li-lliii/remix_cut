from __future__ import annotations

import json
import uuid
from pathlib import Path

from platform_app.db import connect
from platform_app.repositories.base import now_iso, row_to_dict


class AiTransformTaskRepository:
    def __init__(self, db_path: Path):
        self.db_path = Path(db_path)

    def create(
        self,
        *,
        role_id: str,
        source_video_id: str,
        operations: list[str],
        input_asset_keys: dict[str, str],
        params: dict | None = None,
        status: str = "pending",
    ):
        task_id = str(uuid.uuid4())
        timestamp = now_iso()
        with connect(self.db_path) as connection:
            connection.execute(
                """
                INSERT INTO ai_transform_tasks (
                    id, role_id, source_video_id, status, operations_json,
                    input_asset_keys_json, params_json, output_key, error_message,
                    created_at, started_at, finished_at, deleted_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, '', NULL, ?, NULL, NULL, NULL)
                """,
                (
                    task_id,
                    role_id,
                    source_video_id,
                    status,
                    json.dumps(operations, ensure_ascii=False),
                    json.dumps(input_asset_keys, ensure_ascii=False),
                    json.dumps(params or {}, ensure_ascii=False),
                    timestamp,
                ),
            )
            connection.commit()
            row = connection.execute("SELECT * FROM ai_transform_tasks WHERE id = ?", (task_id,)).fetchone()
        return row_to_dict(row)

    def get(self, task_id: str, *, include_deleted: bool = False):
        query = "SELECT * FROM ai_transform_tasks WHERE id = ?"
        params: list = [task_id]
        if not include_deleted:
            query += " AND deleted_at IS NULL"
        with connect(self.db_path) as connection:
            row = connection.execute(query, params).fetchone()
        return row_to_dict(row)

    def list(self, *, role_id: str | None = None, include_deleted: bool = False):
        query = "SELECT * FROM ai_transform_tasks"
        conditions = []
        params: list = []
        if role_id:
            conditions.append("role_id = ?")
            params.append(role_id)
        if not include_deleted:
            conditions.append("deleted_at IS NULL")
        if conditions:
            query += " WHERE " + " AND ".join(conditions)
        query += " ORDER BY created_at DESC"
        with connect(self.db_path) as connection:
            rows = connection.execute(query, params).fetchall()
        return [row_to_dict(row) for row in rows]

    def update_status(self, task_id: str, *, status: str, error_message: str | None = None):
        timestamp = now_iso()
        with connect(self.db_path) as connection:
            connection.execute(
                """
                UPDATE ai_transform_tasks
                SET status = ?,
                    error_message = ?,
                    started_at = CASE WHEN ? = 'running' AND started_at IS NULL THEN ? ELSE started_at END,
                    finished_at = CASE WHEN ? IN ('success', 'failed', 'cancelled') THEN ? ELSE finished_at END
                WHERE id = ?
                """,
                (status, error_message, status, timestamp, status, timestamp, task_id),
            )
            connection.commit()
            row = connection.execute("SELECT * FROM ai_transform_tasks WHERE id = ?", (task_id,)).fetchone()
        return row_to_dict(row)

    def set_output(self, task_id: str, *, output_key: str, status: str = "success"):
        with connect(self.db_path) as connection:
            connection.execute(
                """
                UPDATE ai_transform_tasks
                SET output_key = ?, status = ?, error_message = NULL, finished_at = ?
                WHERE id = ?
                """,
                (output_key, status, now_iso(), task_id),
            )
            connection.commit()
            row = connection.execute("SELECT * FROM ai_transform_tasks WHERE id = ?", (task_id,)).fetchone()
        return row_to_dict(row)

    def soft_delete(self, task_id: str):
        with connect(self.db_path) as connection:
            connection.execute("UPDATE ai_transform_tasks SET deleted_at = ? WHERE id = ?", (now_iso(), task_id))
            connection.commit()
            row = connection.execute("SELECT * FROM ai_transform_tasks WHERE id = ?", (task_id,)).fetchone()
        return row_to_dict(row)


class AiTransformTaskItemRepository:
    def __init__(self, db_path: Path):
        self.db_path = Path(db_path)

    def create(
        self,
        *,
        task_id: str,
        operation: str,
        workflow_name: str,
        input_params: dict | None = None,
        status: str = "pending",
    ):
        item_id = str(uuid.uuid4())
        timestamp = now_iso()
        with connect(self.db_path) as connection:
            connection.execute(
                """
                INSERT INTO ai_transform_task_items (
                    id, task_id, operation, workflow_name, status, backend_job_id,
                    input_params_json, output_key, error_message, created_at, started_at, finished_at
                ) VALUES (?, ?, ?, ?, ?, '', ?, '', NULL, ?, NULL, NULL)
                """,
                (
                    item_id,
                    task_id,
                    operation,
                    workflow_name,
                    status,
                    json.dumps(input_params or {}, ensure_ascii=False),
                    timestamp,
                ),
            )
            connection.commit()
            row = connection.execute("SELECT * FROM ai_transform_task_items WHERE id = ?", (item_id,)).fetchone()
        return row_to_dict(row)

    def list_by_task(self, task_id: str):
        with connect(self.db_path) as connection:
            rows = connection.execute(
                "SELECT * FROM ai_transform_task_items WHERE task_id = ? ORDER BY created_at ASC",
                (task_id,),
            ).fetchall()
        return [row_to_dict(row) for row in rows]

    def update_status(
        self,
        item_id: str,
        *,
        status: str,
        backend_job_id: str | None = None,
        output_key: str | None = None,
        error_message: str | None = None,
    ):
        timestamp = now_iso()
        with connect(self.db_path) as connection:
            connection.execute(
                """
                UPDATE ai_transform_task_items
                SET status = ?,
                    backend_job_id = COALESCE(?, backend_job_id),
                    output_key = COALESCE(?, output_key),
                    error_message = ?,
                    started_at = CASE WHEN ? IN ('running', 'submitted') AND started_at IS NULL THEN ? ELSE started_at END,
                    finished_at = CASE WHEN ? IN ('success', 'failed', 'cancelled') THEN ? ELSE finished_at END
                WHERE id = ?
                """,
                (status, backend_job_id, output_key, error_message, status, timestamp, status, timestamp, item_id),
            )
            connection.commit()
            row = connection.execute("SELECT * FROM ai_transform_task_items WHERE id = ?", (item_id,)).fetchone()
        return row_to_dict(row)
