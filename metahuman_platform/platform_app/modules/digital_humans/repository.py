from __future__ import annotations

import json
import uuid
from pathlib import Path

from platform_app.db import connect as connect_sqlite
from platform_app.db import init_db as init_sqlite_db
from platform_app.infra.postgres import ensure_digital_human_schema, normalize_postgres_url
from platform_app.repositories.base import now_iso, row_to_dict


def _is_postgres_ref(db_ref) -> bool:
    return str(db_ref).startswith(("postgresql://", "postgresql+"))


def _is_sqlite_url(db_ref) -> bool:
    return str(db_ref).startswith("sqlite:///")


def _sqlite_path(db_ref):
    raw = str(db_ref)
    if raw.startswith("sqlite:///"):
        return raw.removeprefix("sqlite:///")
    return db_ref


class _PostgresConnectionAdapter:
    def __init__(self, database_url: str):
        import psycopg
        from psycopg.rows import dict_row

        self._connection = psycopg.connect(normalize_postgres_url(database_url), row_factory=dict_row)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        self._connection.close()

    def execute(self, sql: str, params: tuple | None = None):
        return self._connection.execute(sql.replace("?", "%s"), params or ())

    def commit(self):
        self._connection.commit()


class DigitalHumanBaseRepository:
    def __init__(self, db_path):
        self.db_ref = str(db_path) if _is_postgres_ref(db_path) or _is_sqlite_url(db_path) else db_path
        if _is_postgres_ref(self.db_ref):
            ensure_digital_human_schema(str(self.db_ref))
        else:
            sqlite_path = Path(_sqlite_path(self.db_ref))
            sqlite_path.parent.mkdir(parents=True, exist_ok=True)
            init_sqlite_db(sqlite_path)

    def connection(self):
        if _is_postgres_ref(self.db_ref):
            return _PostgresConnectionAdapter(str(self.db_ref))
        sqlite_path = Path(_sqlite_path(self.db_ref))
        sqlite_path.parent.mkdir(parents=True, exist_ok=True)
        return connect_sqlite(sqlite_path)


class DigitalHumanRepository(DigitalHumanBaseRepository):
    def create(self, *, name: str, avatar_type: str, gender: str, status: str):
        digital_human_id = str(uuid.uuid4())
        timestamp = now_iso()
        with self.connection() as connection:
            connection.execute(
                """
                INSERT INTO digital_humans (
                    id, name, avatar_type, gender, status, primary_asset_id, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, NULL, ?, ?)
                """,
                (
                    digital_human_id,
                    name,
                    avatar_type,
                    gender,
                    status,
                    timestamp,
                    timestamp,
                ),
            )
            connection.commit()
            row = connection.execute(
                "SELECT * FROM digital_humans WHERE id = ?",
                (digital_human_id,),
            ).fetchone()
        return row_to_dict(row)

    def get(self, digital_human_id: str):
        with self.connection() as connection:
            row = connection.execute(
                "SELECT * FROM digital_humans WHERE id = ?",
                (digital_human_id,),
            ).fetchone()
        return row_to_dict(row)

    def list(self):
        with self.connection() as connection:
            rows = connection.execute(
                "SELECT * FROM digital_humans ORDER BY updated_at DESC"
            ).fetchall()
        return [row_to_dict(row) for row in rows]

    def update_primary_asset(self, digital_human_id: str, asset_id: str, *, status: str = "active"):
        timestamp = now_iso()
        with self.connection() as connection:
            connection.execute(
                """
                UPDATE digital_humans
                SET primary_asset_id = ?, status = ?, updated_at = ?
                WHERE id = ?
                """,
                (asset_id, status, timestamp, digital_human_id),
            )
            connection.commit()
            row = connection.execute(
                "SELECT * FROM digital_humans WHERE id = ?",
                (digital_human_id,),
            ).fetchone()
        return row_to_dict(row)


class DigitalHumanProfileRepository(DigitalHumanBaseRepository):
    def create(
        self,
        *,
        digital_human_id: str,
        department: str,
        organization: str,
        speaker_name: str,
        tags: list[str],
        style: str,
        description: str,
        metadata: dict | None = None,
    ):
        profile_id = str(uuid.uuid4())
        timestamp = now_iso()
        with self.connection() as connection:
            connection.execute(
                """
                INSERT INTO digital_human_profiles (
                    id, digital_human_id, department, organization, speaker_name,
                    tags_json, style, description, metadata_json, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    profile_id,
                    digital_human_id,
                    department,
                    organization,
                    speaker_name,
                    json.dumps(tags, ensure_ascii=False),
                    style,
                    description,
                    json.dumps(metadata or {}, ensure_ascii=False),
                    timestamp,
                    timestamp,
                ),
            )
            connection.commit()
            row = connection.execute(
                "SELECT * FROM digital_human_profiles WHERE id = ?",
                (profile_id,),
            ).fetchone()
        return row_to_dict(row)

    def get_by_digital_human(self, digital_human_id: str):
        with self.connection() as connection:
            row = connection.execute(
                "SELECT * FROM digital_human_profiles WHERE digital_human_id = ?",
                (digital_human_id,),
            ).fetchone()
        return row_to_dict(row)


class DigitalHumanAssetRepository(DigitalHumanBaseRepository):
    def create(
        self,
        *,
        digital_human_id: str,
        asset_type: str,
        filename: str,
        file_path: str,
        content_type: str,
        storage_backend: str = "local",
        storage_key: str = "",
        metadata: dict | None = None,
    ):
        asset_id = str(uuid.uuid4())
        with self.connection() as connection:
            connection.execute(
                """
                INSERT INTO digital_human_assets (
                    id, digital_human_id, asset_type, filename, file_path,
                    content_type, storage_backend, storage_key, metadata_json, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    asset_id,
                    digital_human_id,
                    asset_type,
                    filename,
                    file_path,
                    content_type,
                    storage_backend,
                    storage_key,
                    json.dumps(metadata or {}, ensure_ascii=False),
                    now_iso(),
                ),
            )
            connection.commit()
            row = connection.execute(
                "SELECT * FROM digital_human_assets WHERE id = ?",
                (asset_id,),
            ).fetchone()
        return row_to_dict(row)

    def get_by_storage_key(self, storage_key: str):
        with self.connection() as connection:
            row = connection.execute(
                "SELECT * FROM digital_human_assets WHERE storage_key = ?",
                (storage_key,),
            ).fetchone()
        return row_to_dict(row)

    def get(self, asset_id: str):
        with self.connection() as connection:
            row = connection.execute(
                "SELECT * FROM digital_human_assets WHERE id = ?",
                (asset_id,),
            ).fetchone()
        return row_to_dict(row)

    def list_by_digital_human(self, digital_human_id: str):
        with self.connection() as connection:
            rows = connection.execute(
                """
                SELECT * FROM digital_human_assets
                WHERE digital_human_id = ?
                ORDER BY created_at DESC
                """,
                (digital_human_id,),
            ).fetchall()
        return [row_to_dict(row) for row in rows]


class DigitalHumanGenerationTaskRepository(DigitalHumanBaseRepository):
    def create(
        self,
        *,
        digital_human_id: str,
        task_type: str,
        status: str,
        prompt_text: str,
        workflow_name: str,
        input_asset_keys: dict | None = None,
        params: dict | None = None,
    ):
        task_id = str(uuid.uuid4())
        with self.connection() as connection:
            connection.execute(
                """
                INSERT INTO digital_human_generation_tasks (
                    id, digital_human_id, task_type, status, prompt_text, workflow_name,
                    input_asset_keys_json, backend_job_id, result_key, params_json, result_asset_ids_json,
                    error_message, created_at, started_at, finished_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, '', '', ?, '[]', NULL, ?, NULL, NULL)
                """,
                (
                    task_id,
                    digital_human_id,
                    task_type,
                    status,
                    prompt_text,
                    workflow_name,
                    json.dumps(input_asset_keys or {}, ensure_ascii=False),
                    json.dumps(params or {}, ensure_ascii=False),
                    now_iso(),
                ),
            )
            connection.commit()
            row = connection.execute(
                "SELECT * FROM digital_human_generation_tasks WHERE id = ?",
                (task_id,),
            ).fetchone()
        return row_to_dict(row)

    def set_backend_job(self, task_id: str, *, backend_job_id: str, status: str = "submitted"):
        with self.connection() as connection:
            connection.execute(
                """
                UPDATE digital_human_generation_tasks
                SET backend_job_id = ?, status = ?, error_message = NULL
                WHERE id = ?
                """,
                (backend_job_id, status, task_id),
            )
            connection.commit()
            row = connection.execute(
                "SELECT * FROM digital_human_generation_tasks WHERE id = ?",
                (task_id,),
            ).fetchone()
        return row_to_dict(row)

    def update_status(self, task_id: str, *, status: str, error_message: str | None = None):
        timestamp = now_iso()
        with self.connection() as connection:
            connection.execute(
                """
                UPDATE digital_human_generation_tasks
                SET status = ?,
                    error_message = ?,
                    started_at = CASE WHEN ? = 'running' AND started_at IS NULL THEN ? ELSE started_at END,
                    finished_at = CASE WHEN ? IN ('success', 'failed', 'cancelled') THEN ? ELSE finished_at END
                WHERE id = ?
                """,
                (status, error_message, status, timestamp, status, timestamp, task_id),
            )
            connection.commit()
            row = connection.execute(
                "SELECT * FROM digital_human_generation_tasks WHERE id = ?",
                (task_id,),
            ).fetchone()
        return row_to_dict(row)

    def set_input_asset_keys(self, task_id: str, *, input_asset_keys: dict):
        with self.connection() as connection:
            connection.execute(
                """
                UPDATE digital_human_generation_tasks
                SET input_asset_keys_json = ?
                WHERE id = ?
                """,
                (json.dumps(input_asset_keys, ensure_ascii=False), task_id),
            )
            connection.commit()
            row = connection.execute(
                "SELECT * FROM digital_human_generation_tasks WHERE id = ?",
                (task_id,),
            ).fetchone()
        return row_to_dict(row)

    def set_result(self, task_id: str, *, result_key: str, result_asset_ids: list[str] | None = None):
        with self.connection() as connection:
            connection.execute(
                """
                UPDATE digital_human_generation_tasks
                SET result_key = ?, result_asset_ids_json = ?, status = 'success', finished_at = ?
                WHERE id = ?
                """,
                (
                    result_key,
                    json.dumps(result_asset_ids or [], ensure_ascii=False),
                    now_iso(),
                    task_id,
                ),
            )
            connection.commit()
            row = connection.execute(
                "SELECT * FROM digital_human_generation_tasks WHERE id = ?",
                (task_id,),
            ).fetchone()
        return row_to_dict(row)

    def get(self, task_id: str):
        with self.connection() as connection:
            row = connection.execute(
                "SELECT * FROM digital_human_generation_tasks WHERE id = ?",
                (task_id,),
            ).fetchone()
        return row_to_dict(row)

    def list_by_digital_human(self, digital_human_id: str):
        with self.connection() as connection:
            rows = connection.execute(
                """
                SELECT * FROM digital_human_generation_tasks
                WHERE digital_human_id = ?
                ORDER BY created_at DESC
                """,
                (digital_human_id,),
            ).fetchall()
        return [row_to_dict(row) for row in rows]
