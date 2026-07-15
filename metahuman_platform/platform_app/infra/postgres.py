from __future__ import annotations

from dataclasses import dataclass

from platform_app.settings import get_settings


@dataclass(frozen=True)
class DatabaseConfig:
    url: str
    is_postgres: bool


def get_database_config() -> DatabaseConfig:
    url = get_settings().database_url
    return DatabaseConfig(url=url, is_postgres=url.startswith(("postgresql://", "postgresql+")))


DIGITAL_HUMAN_SCHEMA = """
CREATE TABLE IF NOT EXISTS digital_humans (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    avatar_type TEXT NOT NULL DEFAULT '',
    gender TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'draft',
    primary_asset_id TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS digital_human_profiles (
    id TEXT PRIMARY KEY,
    digital_human_id TEXT NOT NULL UNIQUE REFERENCES digital_humans(id),
    department TEXT NOT NULL DEFAULT '',
    organization TEXT NOT NULL DEFAULT '',
    speaker_name TEXT NOT NULL DEFAULT '',
    tags_json JSONB NOT NULL DEFAULT '[]'::jsonb,
    style TEXT NOT NULL DEFAULT '',
    description TEXT NOT NULL DEFAULT '',
    metadata_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS digital_human_assets (
    id TEXT PRIMARY KEY,
    digital_human_id TEXT NOT NULL REFERENCES digital_humans(id),
    asset_type TEXT NOT NULL,
    filename TEXT NOT NULL,
    file_path TEXT NOT NULL,
    content_type TEXT NOT NULL DEFAULT '',
    storage_backend TEXT NOT NULL DEFAULT 'local',
    storage_key TEXT NOT NULL DEFAULT '',
    metadata_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS digital_human_generation_tasks (
    id TEXT PRIMARY KEY,
    digital_human_id TEXT NOT NULL REFERENCES digital_humans(id),
    task_type TEXT NOT NULL,
    status TEXT NOT NULL,
    prompt_text TEXT NOT NULL DEFAULT '',
    workflow_name TEXT NOT NULL DEFAULT '',
    input_asset_keys_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    backend_job_id TEXT NOT NULL DEFAULT '',
    result_key TEXT NOT NULL DEFAULT '',
    params_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    result_asset_ids_json JSONB NOT NULL DEFAULT '[]'::jsonb,
    error_message TEXT,
    created_at TEXT NOT NULL,
    started_at TEXT,
    finished_at TEXT
);
"""


def normalize_postgres_url(url: str) -> str:
    if url.startswith("postgresql+psycopg://"):
        return "postgresql://" + url.removeprefix("postgresql+psycopg://")
    return url


def ensure_digital_human_schema(database_url: str) -> None:
    try:
        import psycopg
    except ModuleNotFoundError as exc:
        raise RuntimeError("psycopg 依赖未安装，无法使用 PostgreSQL") from exc

    with psycopg.connect(normalize_postgres_url(database_url)) as connection:
        connection.execute(DIGITAL_HUMAN_SCHEMA)
        connection.commit()
