from __future__ import annotations

import json
import uuid
from pathlib import Path

from platform_app.db import connect
from platform_app.repositories.base import now_iso, row_to_dict


class MaterialAssetRepository:
    def __init__(self, db_path: Path):
        self.db_path = Path(db_path)

    def create(
        self,
        *,
        asset_type: str,
        partition_name: str,
        source_type: str = "user_upload",
        visibility: str = "private",
        owner_user_id: str = "",
        filename: str,
        file_path: str,
        content_type: str,
        owner_role_id: str = "",
        title: str = "",
        storage_backend: str = "local",
        storage_key: str = "",
        duration_sec: float = 0.0,
        aspect_ratio: str = "unknown",
        width: int = 0,
        height: int = 0,
        tags: list[str] | None = None,
        status: str = "active",
        metadata: dict | None = None,
        asset_id: str | None = None,
    ):
        asset_id = asset_id or str(uuid.uuid4())
        timestamp = now_iso()
        with connect(self.db_path) as connection:
            connection.execute(
                """
                INSERT INTO material_assets (
                    id, asset_type, partition_name, source_type, visibility, owner_user_id,
                    owner_role_id, title, filename, file_path, content_type, storage_backend,
                    storage_key, duration_sec, aspect_ratio, width, height, tags_json,
                    metadata_json, status, created_at, updated_at, deleted_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL)
                """,
                (
                    asset_id,
                    asset_type,
                    partition_name,
                    source_type,
                    visibility,
                    owner_user_id,
                    owner_role_id,
                    title or filename,
                    filename,
                    file_path,
                    content_type,
                    storage_backend,
                    storage_key,
                    duration_sec,
                    aspect_ratio,
                    int(width or 0),
                    int(height or 0),
                    json.dumps(tags or [], ensure_ascii=False),
                    json.dumps(metadata or {}, ensure_ascii=False),
                    status,
                    timestamp,
                    timestamp,
                ),
            )
            connection.commit()
            row = connection.execute("SELECT * FROM material_assets WHERE id = ?", (asset_id,)).fetchone()
        return row_to_dict(row)

    def get(self, asset_id: str, *, include_deleted: bool = False):
        query = "SELECT * FROM material_assets WHERE id = ?"
        params = [asset_id]
        if not include_deleted:
            query += " AND deleted_at IS NULL"
        with connect(self.db_path) as connection:
            row = connection.execute(query, params).fetchone()
        return row_to_dict(row)

    def list(
        self,
        *,
        asset_type: str | None = None,
        partition_name: str | None = None,
        source_type: str | None = None,
        visibility: str | None = None,
        owner_user_id: str | None = None,
        owner_role_id: str | None = None,
        status: str | None = "active",
        include_deleted: bool = False,
    ):
        query = "SELECT * FROM material_assets"
        conditions = []
        params: list = []
        if asset_type:
            conditions.append("asset_type = ?")
            params.append(asset_type)
        if partition_name:
            conditions.append("partition_name = ?")
            params.append(partition_name)
        if source_type:
            conditions.append("source_type = ?")
            params.append(source_type)
        if visibility:
            conditions.append("visibility = ?")
            params.append(visibility)
        if owner_user_id:
            conditions.append("owner_user_id = ?")
            params.append(owner_user_id)
        if owner_role_id:
            conditions.append("owner_role_id = ?")
            params.append(owner_role_id)
        if status:
            conditions.append("status = ?")
            params.append(status)
        if not include_deleted:
            conditions.append("deleted_at IS NULL")
        if conditions:
            query += " WHERE " + " AND ".join(conditions)
        query += " ORDER BY created_at DESC"
        with connect(self.db_path) as connection:
            rows = connection.execute(query, params).fetchall()
        return [row_to_dict(row) for row in rows]

    def soft_delete(self, asset_id: str):
        with connect(self.db_path) as connection:
            connection.execute("UPDATE material_assets SET deleted_at = ? WHERE id = ?", (now_iso(), asset_id))
            connection.commit()
            row = connection.execute("SELECT * FROM material_assets WHERE id = ?", (asset_id,)).fetchone()
        return row_to_dict(row)
