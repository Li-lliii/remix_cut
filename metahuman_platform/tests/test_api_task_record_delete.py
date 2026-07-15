import sqlite3

import pytest

from conftest import app_client
from platform_app.db import init_db
from platform_app.settings import get_settings


@pytest.mark.anyio
async def test_delete_task_record_hides_task_but_keeps_final_video_and_file(tmp_path, monkeypatch):
    monkeypatch.setenv("BS_MEDIA_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("BS_MEDIA_UPLOADS_DIR", str(tmp_path / "uploads"))
    monkeypatch.setenv("BS_MEDIA_DEFAULT_ASR_MODE", "mock")
    monkeypatch.setenv("BS_MEDIA_WORK_DIR", str(tmp_path / "work"))
    monkeypatch.setenv("BS_MEDIA_TEMP_DIR", str(tmp_path / "temp"))
    monkeypatch.setenv("BS_MEDIA_GENERATED_DIR", str(tmp_path / "generated"))

    final_path = tmp_path / "generated" / "keep-final.mp4"
    final_path.parent.mkdir(parents=True, exist_ok=True)
    final_path.write_bytes(b"final")

    init_db(get_settings().database_path)
    connection = sqlite3.connect(get_settings().database_path)
    try:
        connection.execute(
            """
            INSERT INTO roles (id, name, avatar_url, description, tags, created_at, updated_at)
            VALUES ('role-r', '角色R', '', '', '[]', '2026-03-18T09:00:00+00:00', '2026-03-18T09:00:00+00:00')
            """
        )
        connection.execute(
            """
            INSERT INTO role_videos (
                id, role_id, title, file_path, thumbnail_url, duration_sec, aspect_ratio,
                is_pinned, uploaded_at, deleted_at, asr_status, asr_error_message
            ) VALUES ('video-r', 'role-r', 'source.mp4', '/tmp/source.mp4', '', 10, '16:9', 0,
                      '2026-03-18T09:00:00+00:00', NULL, 'success', NULL)
            """
        )
        connection.execute(
            """
            INSERT INTO remix_tasks (
                id, role_id, source_video_id, task_batch_no, prompt_text, product_doc_url,
                target_count, is_max_mode, aspect_mode, resolution, subtitle_enabled, status,
                running_count, success_count, failed_count, created_at, finished_at, error_message, deleted_at
            ) VALUES ('task-r', 'role-r', 'video-r', 'b', 'p', '', 1, 0, 'default', '720p', 1,
                      'success', 0, 1, 0, '2026-03-18T09:01:00+00:00', NULL, NULL, NULL)
            """
        )
        connection.execute(
            """
            INSERT INTO remix_task_items (
                id, remix_task_id, segment_id, comfy_prompt_id, rewritten_text, tts_audio_path, output_video_url,
                status, error_message, created_at, finished_at, final_deleted_at
            ) VALUES ('item-r', 'task-r', 'seg', 'pid', 'script', '/tmp/a.wav', ?, 'success',
                      NULL, '2026-03-18T09:01:10+00:00', NULL, NULL)
            """,
            (str(final_path),),
        )
        connection.commit()
    finally:
        connection.close()

    async with app_client() as client:
        before_tasks = await client.get("/api/remix/tasks", params={"role_id": "role-r"})
        assert [item["id"] for item in before_tasks.json()["items"]] == ["task-r"]

        before_final = await client.get("/api/final-videos", params={"role_id": "role-r"})
        assert [item["id"] for item in before_final.json()["items"]] == ["remix:item-r"]

        deleted_task = await client.delete("/api/remix/tasks/task-r", params={"role_id": "role-r"})
        assert deleted_task.status_code == 200

        after_tasks = await client.get("/api/remix/tasks", params={"role_id": "role-r"})
        assert after_tasks.json()["items"] == []

        # 删除任务记录不应影响成片预览聚合，也不应删除成片文件
        after_final = await client.get("/api/final-videos", params={"role_id": "role-r"})
        assert [item["id"] for item in after_final.json()["items"]] == ["remix:item-r"]

    assert final_path.exists()


@pytest.mark.anyio
async def test_delete_running_preprocess_job_is_rejected(tmp_path, monkeypatch):
    monkeypatch.setenv("BS_MEDIA_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("BS_MEDIA_UPLOADS_DIR", str(tmp_path / "uploads"))
    monkeypatch.setenv("BS_MEDIA_DEFAULT_ASR_MODE", "mock")
    monkeypatch.setenv("BS_MEDIA_WORK_DIR", str(tmp_path / "work"))
    monkeypatch.setenv("BS_MEDIA_TEMP_DIR", str(tmp_path / "temp"))
    monkeypatch.setenv("BS_MEDIA_GENERATED_DIR", str(tmp_path / "generated"))

    init_db(get_settings().database_path)
    connection = sqlite3.connect(get_settings().database_path)
    try:
        connection.execute(
            """
            INSERT INTO roles (id, name, avatar_url, description, tags, created_at, updated_at)
            VALUES ('role-p', '角色P', '', '', '[]', '2026-03-18T09:00:00+00:00', '2026-03-18T09:00:00+00:00')
            """
        )
        connection.execute(
            """
            INSERT INTO role_videos (
                id, role_id, title, file_path, thumbnail_url, duration_sec, aspect_ratio,
                is_pinned, uploaded_at, deleted_at, asr_status, asr_error_message
            ) VALUES ('video-p', 'role-p', 'source.mp4', '/tmp/source.mp4', '', 10, '16:9', 0,
                      '2026-03-18T09:00:00+00:00', NULL, 'success', NULL)
            """
        )
        connection.execute(
            """
            INSERT INTO video_preprocess_jobs (
                id, role_video_id, job_type, status, progress, error_message, started_at, finished_at, deleted_at
            ) VALUES ('job-p', 'video-p', 'remix', 'running', 10, NULL, '2026-03-18T09:01:00+00:00', NULL, NULL)
            """
        )
        connection.commit()
    finally:
        connection.close()

    async with app_client() as client:
        response = await client.delete("/api/remix/preprocess-jobs/job-p", params={"role_id": "role-p"})
        assert response.status_code == 404
        assert "不能删除" in response.text

        jobs = await client.get("/api/remix/preprocess-jobs", params={"role_id": "role-p"})
        assert jobs.status_code == 200
        assert jobs.json()["items"]


@pytest.mark.anyio
async def test_batch_delete_lip_sync_tasks_deletes_only_terminal(tmp_path, monkeypatch):
    monkeypatch.setenv("BS_MEDIA_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("BS_MEDIA_UPLOADS_DIR", str(tmp_path / "uploads"))
    monkeypatch.setenv("BS_MEDIA_DEFAULT_ASR_MODE", "mock")
    monkeypatch.setenv("BS_MEDIA_WORK_DIR", str(tmp_path / "work"))
    monkeypatch.setenv("BS_MEDIA_TEMP_DIR", str(tmp_path / "temp"))
    monkeypatch.setenv("BS_MEDIA_GENERATED_DIR", str(tmp_path / "generated"))

    init_db(get_settings().database_path)
    connection = sqlite3.connect(get_settings().database_path)
    try:
        connection.execute(
            """
            INSERT INTO roles (id, name, avatar_url, description, tags, created_at, updated_at)
            VALUES ('role-l', '角色L', '', '', '[]', '2026-03-18T09:00:00+00:00', '2026-03-18T09:00:00+00:00')
            """
        )
        connection.execute(
            """
            INSERT INTO role_videos (
                id, role_id, title, file_path, thumbnail_url, duration_sec, aspect_ratio,
                is_pinned, uploaded_at, deleted_at, asr_status, asr_error_message
            ) VALUES ('video-l', 'role-l', 'source.mp4', '/tmp/source.mp4', '', 10, '16:9', 0,
                      '2026-03-18T09:00:00+00:00', NULL, 'success', NULL)
            """
        )
        connection.execute(
            """
            INSERT INTO lip_sync_tasks (
                id, project_id, role_id, base_video_id, selected_script_id, final_script_text,
                video_job_id, aspect_mode, resolution, subtitle_enabled, status, tts_audio_path,
                output_video_url, error_message, created_at, finished_at, deleted_at, final_deleted_at
            ) VALUES ('lip-ok', 'p', 'role-l', 'video-l', 's', 'hello', 'job', 'default', '720p', 1,
                      'success', '/tmp/a.wav', '/tmp/a.mp4', NULL, '2026-03-18T09:01:00+00:00', NULL, NULL, NULL)
            """
        )
        connection.execute(
            """
            INSERT INTO lip_sync_tasks (
                id, project_id, role_id, base_video_id, selected_script_id, final_script_text,
                video_job_id, aspect_mode, resolution, subtitle_enabled, status, tts_audio_path,
                output_video_url, error_message, created_at, finished_at, deleted_at, final_deleted_at
            ) VALUES ('lip-run', 'p', 'role-l', 'video-l', 's', 'hello', 'job', 'default', '720p', 1,
                      'video_generating', '/tmp/a.wav', '/tmp/a.mp4', NULL, '2026-03-18T09:01:00+00:00', NULL, NULL, NULL)
            """
        )
        connection.commit()
    finally:
        connection.close()

    async with app_client() as client:
        response = await client.post("/api/lip-sync/tasks/batch-delete", json={"role_id": "role-l", "ids": ["lip-ok", "lip-run"]})
        assert response.status_code == 200
        body = response.json()
        assert body["deleted_count"] == 1
        assert body["failed_count"] == 1

        tasks = await client.get("/api/lip-sync/tasks", params={"role_id": "role-l"})
        # running 任务仍在
        assert {item["id"] for item in tasks.json()["items"]} == {"lip-run"}


@pytest.mark.anyio
async def test_batch_delete_remix_tasks_deletes_only_terminal(tmp_path, monkeypatch):
    monkeypatch.setenv("BS_MEDIA_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("BS_MEDIA_UPLOADS_DIR", str(tmp_path / "uploads"))
    monkeypatch.setenv("BS_MEDIA_DEFAULT_ASR_MODE", "mock")
    monkeypatch.setenv("BS_MEDIA_WORK_DIR", str(tmp_path / "work"))
    monkeypatch.setenv("BS_MEDIA_TEMP_DIR", str(tmp_path / "temp"))
    monkeypatch.setenv("BS_MEDIA_GENERATED_DIR", str(tmp_path / "generated"))

    init_db(get_settings().database_path)
    connection = sqlite3.connect(get_settings().database_path)
    try:
        connection.execute(
            """
            INSERT INTO roles (id, name, avatar_url, description, tags, created_at, updated_at)
            VALUES ('role-rb', '角色RB', '', '', '[]', '2026-03-18T09:00:00+00:00', '2026-03-18T09:00:00+00:00')
            """
        )
        connection.execute(
            """
            INSERT INTO role_videos (
                id, role_id, title, file_path, thumbnail_url, duration_sec, aspect_ratio,
                is_pinned, uploaded_at, deleted_at, asr_status, asr_error_message
            ) VALUES ('video-rb', 'role-rb', 'source.mp4', '/tmp/source.mp4', '', 10, '16:9', 0,
                      '2026-03-18T09:00:00+00:00', NULL, 'success', NULL)
            """
        )
        connection.execute(
            """
            INSERT INTO remix_tasks (
                id, role_id, source_video_id, task_batch_no, prompt_text, product_doc_url,
                target_count, is_max_mode, aspect_mode, resolution, subtitle_enabled, status,
                running_count, success_count, failed_count, created_at, finished_at, error_message, deleted_at
            ) VALUES ('task-ok', 'role-rb', 'video-rb', 'b-ok', 'p', '', 1, 0, 'default', '720p', 1,
                      'success', 0, 1, 0, '2026-03-18T09:01:00+00:00', NULL, NULL, NULL)
            """
        )
        connection.execute(
            """
            INSERT INTO remix_tasks (
                id, role_id, source_video_id, task_batch_no, prompt_text, product_doc_url,
                target_count, is_max_mode, aspect_mode, resolution, subtitle_enabled, status,
                running_count, success_count, failed_count, created_at, finished_at, error_message, deleted_at
            ) VALUES ('task-run', 'role-rb', 'video-rb', 'b-run', 'p', '', 1, 0, 'default', '720p', 1,
                      'video_generating', 1, 0, 0, '2026-03-18T09:02:00+00:00', NULL, NULL, NULL)
            """
        )
        connection.commit()
    finally:
        connection.close()

    async with app_client() as client:
        response = await client.post("/api/remix/tasks/batch-delete", json={"role_id": "role-rb", "ids": ["task-ok", "task-run"]})
        assert response.status_code == 200
        body = response.json()
        assert body["deleted_count"] == 1
        assert body["failed_count"] == 1
        assert body["failed_ids"] == ["task-run"]

        tasks = await client.get("/api/remix/tasks", params={"role_id": "role-rb"})
        assert {item["id"] for item in tasks.json()["items"]} == {"task-run"}
