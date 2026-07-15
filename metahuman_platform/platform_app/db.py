import sqlite3
from pathlib import Path


SCHEMA = """
CREATE TABLE IF NOT EXISTS roles (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    avatar_url TEXT NOT NULL DEFAULT '',
    description TEXT NOT NULL DEFAULT '',
    tags TEXT NOT NULL DEFAULT '[]',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS role_videos (
    id TEXT PRIMARY KEY,
    role_id TEXT NOT NULL,
    title TEXT NOT NULL,
    file_path TEXT NOT NULL,
    thumbnail_url TEXT NOT NULL DEFAULT '',
    duration_sec REAL NOT NULL DEFAULT 0,
    aspect_ratio TEXT NOT NULL DEFAULT 'unknown',
    is_pinned INTEGER NOT NULL DEFAULT 0,
    uploaded_at TEXT NOT NULL,
    deleted_at TEXT,
    asr_status TEXT NOT NULL DEFAULT 'pending',
    asr_error_message TEXT,
    FOREIGN KEY (role_id) REFERENCES roles(id)
);

CREATE TABLE IF NOT EXISTS video_asr_results (
    id TEXT PRIMARY KEY,
    role_video_id TEXT NOT NULL UNIQUE,
    full_text TEXT NOT NULL,
    segments_json TEXT NOT NULL,
    summary_text TEXT NOT NULL DEFAULT '',
    summary_status TEXT NOT NULL DEFAULT 'pending',
    summary_error_message TEXT,
    summary_updated_at TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY (role_video_id) REFERENCES role_videos(id)
);

CREATE TABLE IF NOT EXISTS video_preprocess_jobs (
    id TEXT PRIMARY KEY,
    role_video_id TEXT NOT NULL,
    job_type TEXT NOT NULL,
    status TEXT NOT NULL,
    progress INTEGER NOT NULL DEFAULT 0,
    error_message TEXT,
    started_at TEXT NOT NULL,
    finished_at TEXT,
    deleted_at TEXT,
    FOREIGN KEY (role_video_id) REFERENCES role_videos(id)
);

CREATE TABLE IF NOT EXISTS smart_clip_projects (
    id TEXT PRIMARY KEY,
    role_id TEXT NOT NULL,
    source_video_id TEXT NOT NULL,
    source_video_title TEXT NOT NULL,
    status TEXT NOT NULL,
    stage TEXT NOT NULL,
    total_asr_segments INTEGER NOT NULL DEFAULT 0,
    kept_sales_segments INTEGER NOT NULL DEFAULT 0,
    candidate_clip_count INTEGER NOT NULL DEFAULT 0,
    export_total_count INTEGER NOT NULL DEFAULT 0,
    export_completed_count INTEGER NOT NULL DEFAULT 0,
    export_current_index INTEGER NOT NULL DEFAULT 0,
    error_message TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY (role_id) REFERENCES roles(id),
    FOREIGN KEY (source_video_id) REFERENCES role_videos(id)
);

CREATE TABLE IF NOT EXISTS smart_clip_segments (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL,
    source_video_id TEXT NOT NULL,
    start_sec REAL NOT NULL,
    end_sec REAL NOT NULL,
    duration_sec REAL NOT NULL,
    asr_text TEXT NOT NULL,
    classification TEXT NOT NULL,
    keep_flag INTEGER NOT NULL DEFAULT 1,
    reason TEXT,
    created_at TEXT NOT NULL,
    FOREIGN KEY (project_id) REFERENCES smart_clip_projects(id),
    FOREIGN KEY (source_video_id) REFERENCES role_videos(id)
);

CREATE TABLE IF NOT EXISTS smart_clip_candidates (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL,
    clip_index INTEGER NOT NULL,
    title TEXT NOT NULL,
    duration_sec REAL NOT NULL,
    segment_refs_json TEXT NOT NULL,
    source_time_ranges_json TEXT NOT NULL,
    preview_text TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL,
    output_video_path TEXT,
    error_message TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY (project_id) REFERENCES smart_clip_projects(id)
);

CREATE TABLE IF NOT EXISTS remix_segments (
    id TEXT PRIMARY KEY,
    role_id TEXT NOT NULL,
    source_video_id TEXT NOT NULL,
    segment_file_path TEXT NOT NULL,
    start_sec REAL NOT NULL,
    end_sec REAL NOT NULL,
    duration_sec REAL NOT NULL,
    asr_text TEXT NOT NULL,
    created_at TEXT NOT NULL,
    FOREIGN KEY (role_id) REFERENCES roles(id),
    FOREIGN KEY (source_video_id) REFERENCES role_videos(id)
);

CREATE TABLE IF NOT EXISTS remix_tasks (
    id TEXT PRIMARY KEY,
    role_id TEXT NOT NULL,
    source_video_id TEXT NOT NULL,
    task_batch_no TEXT NOT NULL,
    prompt_text TEXT NOT NULL,
    product_doc_url TEXT NOT NULL DEFAULT '',
    target_count INTEGER NOT NULL,
    is_max_mode INTEGER NOT NULL DEFAULT 0,
    aspect_mode TEXT NOT NULL,
    resolution TEXT NOT NULL,
    subtitle_enabled INTEGER NOT NULL DEFAULT 0,
    status TEXT NOT NULL,
    error_message TEXT,
    running_count INTEGER NOT NULL DEFAULT 0,
    success_count INTEGER NOT NULL DEFAULT 0,
    failed_count INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    finished_at TEXT,
    deleted_at TEXT,
    FOREIGN KEY (role_id) REFERENCES roles(id),
    FOREIGN KEY (source_video_id) REFERENCES role_videos(id)
);

CREATE TABLE IF NOT EXISTS remix_task_items (
    id TEXT PRIMARY KEY,
    remix_task_id TEXT NOT NULL,
    segment_id TEXT NOT NULL,
    comfy_prompt_id TEXT,
    rewritten_text TEXT,
    tts_audio_path TEXT,
    output_video_url TEXT,
    status TEXT NOT NULL,
    error_message TEXT,
    created_at TEXT NOT NULL,
    finished_at TEXT,
    final_deleted_at TEXT,
    FOREIGN KEY (remix_task_id) REFERENCES remix_tasks(id),
    FOREIGN KEY (segment_id) REFERENCES remix_segments(id)
);

CREATE TABLE IF NOT EXISTS review_records (
    id TEXT PRIMARY KEY,
    source_type TEXT NOT NULL,
    source_task_id TEXT NOT NULL,
    status TEXT NOT NULL,
    review_note TEXT NOT NULL DEFAULT '',
    reviewed_at TEXT
);

CREATE TABLE IF NOT EXISTS lip_sync_projects (
    id TEXT PRIMARY KEY,
    role_id TEXT NOT NULL,
    base_video_id TEXT NOT NULL,
    prompt_text TEXT NOT NULL,
    product_doc_url TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL,
    created_at TEXT NOT NULL,
    FOREIGN KEY (role_id) REFERENCES roles(id),
    FOREIGN KEY (base_video_id) REFERENCES role_videos(id)
);

CREATE TABLE IF NOT EXISTS script_candidates (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL,
    content TEXT NOT NULL,
    char_count INTEGER NOT NULL DEFAULT 0,
    estimated_tts_duration_sec REAL NOT NULL DEFAULT 0,
    version_no INTEGER NOT NULL DEFAULT 1,
    is_selected INTEGER NOT NULL DEFAULT 0,
    edited_content TEXT,
    is_edited INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    FOREIGN KEY (project_id) REFERENCES lip_sync_projects(id)
);

CREATE TABLE IF NOT EXISTS lip_sync_tasks (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL,
    role_id TEXT NOT NULL,
    base_video_id TEXT NOT NULL,
    selected_script_id TEXT NOT NULL,
    final_script_text TEXT NOT NULL,
    video_job_id TEXT,
    aspect_mode TEXT NOT NULL,
    resolution TEXT NOT NULL,
    subtitle_enabled INTEGER NOT NULL DEFAULT 0,
    status TEXT NOT NULL,
    tts_audio_path TEXT,
    output_video_url TEXT,
    error_message TEXT,
    created_at TEXT NOT NULL,
    finished_at TEXT,
    deleted_at TEXT,
    final_deleted_at TEXT,
    FOREIGN KEY (project_id) REFERENCES lip_sync_projects(id),
    FOREIGN KEY (role_id) REFERENCES roles(id),
    FOREIGN KEY (base_video_id) REFERENCES role_videos(id),
    FOREIGN KEY (selected_script_id) REFERENCES script_candidates(id)
);

CREATE TABLE IF NOT EXISTS role_product_docs (
    id TEXT PRIMARY KEY,
    role_id TEXT NOT NULL,
    name TEXT NOT NULL,
    file_path TEXT NOT NULL,
    content TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    deleted_at TEXT,
    FOREIGN KEY (role_id) REFERENCES roles(id)
);

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
    digital_human_id TEXT NOT NULL UNIQUE,
    department TEXT NOT NULL DEFAULT '',
    organization TEXT NOT NULL DEFAULT '',
    speaker_name TEXT NOT NULL DEFAULT '',
    tags_json TEXT NOT NULL DEFAULT '[]',
    style TEXT NOT NULL DEFAULT '',
    description TEXT NOT NULL DEFAULT '',
    metadata_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY (digital_human_id) REFERENCES digital_humans(id)
);

CREATE TABLE IF NOT EXISTS digital_human_assets (
    id TEXT PRIMARY KEY,
    digital_human_id TEXT NOT NULL,
    asset_type TEXT NOT NULL,
    filename TEXT NOT NULL,
    file_path TEXT NOT NULL,
    content_type TEXT NOT NULL DEFAULT '',
    storage_backend TEXT NOT NULL DEFAULT 'local',
    storage_key TEXT NOT NULL DEFAULT '',
    metadata_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL,
    FOREIGN KEY (digital_human_id) REFERENCES digital_humans(id)
);

CREATE TABLE IF NOT EXISTS digital_human_generation_tasks (
    id TEXT PRIMARY KEY,
    digital_human_id TEXT NOT NULL,
    task_type TEXT NOT NULL,
    status TEXT NOT NULL,
    prompt_text TEXT NOT NULL DEFAULT '',
    workflow_name TEXT NOT NULL DEFAULT '',
    input_asset_keys_json TEXT NOT NULL DEFAULT '{}',
    backend_job_id TEXT NOT NULL DEFAULT '',
    result_key TEXT NOT NULL DEFAULT '',
    params_json TEXT NOT NULL DEFAULT '{}',
    result_asset_ids_json TEXT NOT NULL DEFAULT '[]',
    error_message TEXT,
    created_at TEXT NOT NULL,
    started_at TEXT,
    finished_at TEXT,
    FOREIGN KEY (digital_human_id) REFERENCES digital_humans(id)
);
"""


def connect(db_path: Path) -> sqlite3.Connection:
    connection = sqlite3.connect(str(db_path), check_same_thread=False)
    connection.row_factory = sqlite3.Row
    return connection


def init_db(db_path: Path) -> None:
    db_path = Path(db_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    with connect(db_path) as connection:
        connection.executescript(SCHEMA)
        remix_item_columns = {
            row["name"] for row in connection.execute("PRAGMA table_info(remix_task_items)").fetchall()
        }
        if "comfy_prompt_id" not in remix_item_columns:
            connection.execute("ALTER TABLE remix_task_items ADD COLUMN comfy_prompt_id TEXT")
        remix_task_columns = {
            row["name"] for row in connection.execute("PRAGMA table_info(remix_tasks)").fetchall()
        }
        if "error_message" not in remix_task_columns:
            connection.execute("ALTER TABLE remix_tasks ADD COLUMN error_message TEXT")
        if "deleted_at" not in remix_task_columns:
            connection.execute("ALTER TABLE remix_tasks ADD COLUMN deleted_at TEXT")
        preprocess_job_columns = {
            row["name"] for row in connection.execute("PRAGMA table_info(video_preprocess_jobs)").fetchall()
        }
        if "deleted_at" not in preprocess_job_columns:
            connection.execute("ALTER TABLE video_preprocess_jobs ADD COLUMN deleted_at TEXT")
        smart_clip_project_columns = {
            row["name"] for row in connection.execute("PRAGMA table_info(smart_clip_projects)").fetchall()
        }
        if "stage" not in smart_clip_project_columns:
            connection.execute("ALTER TABLE smart_clip_projects ADD COLUMN stage TEXT NOT NULL DEFAULT 'classifying'")
        if "export_current_index" not in smart_clip_project_columns:
            connection.execute(
                "ALTER TABLE smart_clip_projects ADD COLUMN export_current_index INTEGER NOT NULL DEFAULT 0"
            )
        smart_clip_candidate_columns = {
            row["name"] for row in connection.execute("PRAGMA table_info(smart_clip_candidates)").fetchall()
        }
        if "output_video_path" not in smart_clip_candidate_columns:
            connection.execute("ALTER TABLE smart_clip_candidates ADD COLUMN output_video_path TEXT")
        asr_result_columns = {
            row["name"] for row in connection.execute("PRAGMA table_info(video_asr_results)").fetchall()
        }
        if "summary_text" not in asr_result_columns:
            connection.execute("ALTER TABLE video_asr_results ADD COLUMN summary_text TEXT NOT NULL DEFAULT ''")
        if "summary_status" not in asr_result_columns:
            connection.execute(
                "ALTER TABLE video_asr_results ADD COLUMN summary_status TEXT NOT NULL DEFAULT 'pending'"
            )
        if "summary_error_message" not in asr_result_columns:
            connection.execute("ALTER TABLE video_asr_results ADD COLUMN summary_error_message TEXT")
        if "summary_updated_at" not in asr_result_columns:
            connection.execute("ALTER TABLE video_asr_results ADD COLUMN summary_updated_at TEXT")
        lip_sync_task_columns = {
            row["name"] for row in connection.execute("PRAGMA table_info(lip_sync_tasks)").fetchall()
        }
        if "final_script_text" not in lip_sync_task_columns:
            connection.execute("ALTER TABLE lip_sync_tasks ADD COLUMN final_script_text TEXT NOT NULL DEFAULT ''")
        if "video_job_id" not in lip_sync_task_columns:
            connection.execute("ALTER TABLE lip_sync_tasks ADD COLUMN video_job_id TEXT")
        if "deleted_at" not in lip_sync_task_columns:
            connection.execute("ALTER TABLE lip_sync_tasks ADD COLUMN deleted_at TEXT")
        if "final_deleted_at" not in lip_sync_task_columns:
            connection.execute("ALTER TABLE lip_sync_tasks ADD COLUMN final_deleted_at TEXT")
        if "final_deleted_at" not in remix_item_columns:
            connection.execute("ALTER TABLE remix_task_items ADD COLUMN final_deleted_at TEXT")
        digital_human_task_columns = {
            row["name"] for row in connection.execute("PRAGMA table_info(digital_human_generation_tasks)").fetchall()
        }
        if "input_asset_keys_json" not in digital_human_task_columns:
            connection.execute(
                "ALTER TABLE digital_human_generation_tasks ADD COLUMN input_asset_keys_json TEXT NOT NULL DEFAULT '{}'"
            )
        if "backend_job_id" not in digital_human_task_columns:
            connection.execute(
                "ALTER TABLE digital_human_generation_tasks ADD COLUMN backend_job_id TEXT NOT NULL DEFAULT ''"
            )
        if "result_key" not in digital_human_task_columns:
            connection.execute(
                "ALTER TABLE digital_human_generation_tasks ADD COLUMN result_key TEXT NOT NULL DEFAULT ''"
            )
        if "params_json" not in digital_human_task_columns:
            connection.execute(
                "ALTER TABLE digital_human_generation_tasks ADD COLUMN params_json TEXT NOT NULL DEFAULT '{}'"
            )
        digital_human_asset_columns = {
            row["name"] for row in connection.execute("PRAGMA table_info(digital_human_assets)").fetchall()
        }
        if "storage_backend" not in digital_human_asset_columns:
            connection.execute(
                "ALTER TABLE digital_human_assets ADD COLUMN storage_backend TEXT NOT NULL DEFAULT 'local'"
            )
        if "storage_key" not in digital_human_asset_columns:
            connection.execute(
                "ALTER TABLE digital_human_assets ADD COLUMN storage_key TEXT NOT NULL DEFAULT ''"
            )
        connection.commit()
