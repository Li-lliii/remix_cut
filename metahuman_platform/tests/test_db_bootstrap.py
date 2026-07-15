import sqlite3

from platform_app.db import init_db
from platform_app.settings import get_settings


def test_init_db_creates_phase1_and_phase2_tables(tmp_path, monkeypatch):
    db_path = tmp_path / "app.db"

    init_db(db_path)

    connection = sqlite3.connect(db_path)
    try:
        tables = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
        assert {
            "roles",
            "role_videos",
            "video_asr_results",
            "video_preprocess_jobs",
            "smart_clip_projects",
            "smart_clip_segments",
            "smart_clip_candidates",
            "remix_segments",
            "remix_tasks",
            "remix_task_items",
            "review_records",
            "lip_sync_projects",
            "script_candidates",
            "lip_sync_tasks",
            "role_product_docs",
        } <= tables
        assert {
            "video_preprocess_jobs",
            "remix_segments",
            "remix_tasks",
            "remix_task_items",
            "review_records",
        } <= tables

        role_columns = {
            row[1] for row in connection.execute("PRAGMA table_info(roles)").fetchall()
        }
        video_columns = {
            row[1]
            for row in connection.execute("PRAGMA table_info(role_videos)").fetchall()
        }
        asr_columns = {
            row[1]
            for row in connection.execute("PRAGMA table_info(video_asr_results)").fetchall()
        }
        preprocess_columns = {
            row[1]
            for row in connection.execute("PRAGMA table_info(video_preprocess_jobs)").fetchall()
        }
        remix_task_columns = {
            row[1]
            for row in connection.execute("PRAGMA table_info(remix_tasks)").fetchall()
        }
        remix_item_columns = {
            row[1]
            for row in connection.execute("PRAGMA table_info(remix_task_items)").fetchall()
        }
        review_columns = {
            row[1]
            for row in connection.execute("PRAGMA table_info(review_records)").fetchall()
        }
        lip_sync_project_columns = {
            row[1]
            for row in connection.execute("PRAGMA table_info(lip_sync_projects)").fetchall()
        }
        script_candidate_columns = {
            row[1]
            for row in connection.execute("PRAGMA table_info(script_candidates)").fetchall()
        }
        lip_sync_task_columns = {
            row[1]
            for row in connection.execute("PRAGMA table_info(lip_sync_tasks)").fetchall()
        }
        product_doc_columns = {
            row[1]
            for row in connection.execute("PRAGMA table_info(role_product_docs)").fetchall()
        }

        assert "name" in role_columns
        assert "asr_status" in video_columns
        assert "segments_json" in asr_columns
        assert "summary_text" in asr_columns
        assert "summary_status" in asr_columns
        assert "summary_error_message" in asr_columns
        assert "summary_updated_at" in asr_columns
        smart_clip_project_columns = {
            row[1]
            for row in connection.execute("PRAGMA table_info(smart_clip_projects)").fetchall()
        }
        smart_clip_segment_columns = {
            row[1]
            for row in connection.execute("PRAGMA table_info(smart_clip_segments)").fetchall()
        }
        smart_clip_candidate_columns = {
            row[1]
            for row in connection.execute("PRAGMA table_info(smart_clip_candidates)").fetchall()
        }
        assert "progress" in preprocess_columns
        assert "deleted_at" in preprocess_columns
        assert "task_batch_no" in remix_task_columns
        assert "deleted_at" in remix_task_columns
        assert "segment_id" in remix_item_columns
        assert "final_deleted_at" in remix_item_columns
        assert "source_task_id" in review_columns
        assert {"role_id", "base_video_id", "status"} <= lip_sync_project_columns
        assert {"project_id", "content", "edited_content", "estimated_tts_duration_sec"} <= script_candidate_columns
        assert {"project_id", "selected_script_id", "final_script_text", "video_job_id"} <= lip_sync_task_columns
        assert {"deleted_at", "final_deleted_at"} <= lip_sync_task_columns
        assert {"role_id", "name", "file_path", "content"} <= product_doc_columns
        assert {"role_id", "source_video_id", "source_video_title", "status", "stage"} <= smart_clip_project_columns
        assert {"project_id", "source_video_id", "classification", "keep_flag"} <= smart_clip_segment_columns
        assert {"project_id", "clip_index", "segment_refs_json", "status", "output_video_path"} <= smart_clip_candidate_columns
    finally:
        connection.close()


def test_init_db_migrates_existing_video_asr_results_table(tmp_path):
    db_path = tmp_path / "app.db"
    connection = sqlite3.connect(db_path)
    try:
        connection.execute(
            """
            CREATE TABLE video_asr_results (
                id TEXT PRIMARY KEY,
                role_video_id TEXT NOT NULL UNIQUE,
                full_text TEXT NOT NULL,
                segments_json TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
        connection.commit()
    finally:
        connection.close()

    init_db(db_path)

    connection = sqlite3.connect(db_path)
    try:
        asr_columns = {
            row[1]
            for row in connection.execute("PRAGMA table_info(video_asr_results)").fetchall()
        }
        assert "summary_text" in asr_columns
        assert "summary_status" in asr_columns
        assert "summary_error_message" in asr_columns
        assert "summary_updated_at" in asr_columns
    finally:
        connection.close()


def test_init_db_migrates_existing_smart_clip_tables(tmp_path):
    db_path = tmp_path / "app.db"
    connection = sqlite3.connect(db_path)
    try:
        connection.execute(
            """
            CREATE TABLE smart_clip_projects (
                id TEXT PRIMARY KEY,
                role_id TEXT NOT NULL,
                source_video_id TEXT NOT NULL,
                source_video_title TEXT NOT NULL,
                status TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE smart_clip_segments (
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
                created_at TEXT NOT NULL
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE smart_clip_candidates (
                id TEXT PRIMARY KEY,
                project_id TEXT NOT NULL,
                clip_index INTEGER NOT NULL,
                title TEXT NOT NULL,
                duration_sec REAL NOT NULL,
                segment_refs_json TEXT NOT NULL,
                source_time_ranges_json TEXT NOT NULL,
                preview_text TEXT NOT NULL DEFAULT '',
                status TEXT NOT NULL,
                error_message TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
        connection.commit()
    finally:
        connection.close()

    init_db(db_path)

    connection = sqlite3.connect(db_path)
    try:
        project_columns = {
            row[1]
            for row in connection.execute("PRAGMA table_info(smart_clip_projects)").fetchall()
        }
        segment_columns = {
            row[1]
            for row in connection.execute("PRAGMA table_info(smart_clip_segments)").fetchall()
        }
        candidate_columns = {
            row[1]
            for row in connection.execute("PRAGMA table_info(smart_clip_candidates)").fetchall()
        }
        assert "stage" in project_columns
        assert "export_current_index" in project_columns
        assert "output_video_path" in candidate_columns
        assert {"project_id", "source_video_id", "classification", "keep_flag"} <= segment_columns
    finally:
        connection.close()


def test_get_settings_creates_phase2_work_directories(tmp_path, monkeypatch):
    data_dir = tmp_path / "data"
    uploads_dir = tmp_path / "uploads"
    work_dir = tmp_path / "work"
    temp_dir = tmp_path / "scratch"
    generated_dir = tmp_path / "generated"

    monkeypatch.setenv("BS_MEDIA_DATA_DIR", str(data_dir))
    monkeypatch.setenv("BS_MEDIA_UPLOADS_DIR", str(uploads_dir))
    monkeypatch.setenv("BS_MEDIA_WORK_DIR", str(work_dir))
    monkeypatch.setenv("BS_MEDIA_TEMP_DIR", str(temp_dir))
    monkeypatch.setenv("BS_MEDIA_GENERATED_DIR", str(generated_dir))

    settings = get_settings()

    assert settings.work_dir == work_dir.resolve()
    assert settings.temp_dir == temp_dir.resolve()
    assert settings.generated_dir == generated_dir.resolve()
    assert settings.work_dir.exists()
    assert settings.temp_dir.exists()
    assert settings.generated_dir.exists()

    monkeypatch.setenv("BS_MEDIA_DATA_DIR", str(tmp_path / "data"))
    settings = get_settings()
    assert settings.work_dir.exists()
    assert settings.temp_dir.exists()
    assert settings.generated_dir.exists()
