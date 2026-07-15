import sqlite3
from pathlib import Path

import pytest

from conftest import app_client
from platform_app.db import init_db
from platform_app.settings import get_settings


def seed_final_video_rows(db_path):
    root = Path(db_path).parent
    remix_file_a = root / "alpha.mp4"
    remix_file_b = root / "gamma.mp4"
    lip_sync_file = root / "beta.mp4"
    remix_file_a.write_bytes(b"remix-a")
    remix_file_b.write_bytes(b"remix-b")
    lip_sync_file.write_bytes(b"lip-sync")
    connection = sqlite3.connect(db_path)
    try:
        connection.execute(
            """
            INSERT INTO roles (id, name, avatar_url, description, tags, created_at, updated_at)
            VALUES (?, ?, '', '', '[]', ?, ?)
            """,
            ("role-a", "角色A", "2026-03-18T09:00:00+00:00", "2026-03-18T09:00:00+00:00"),
        )
        connection.execute(
            """
            INSERT INTO roles (id, name, avatar_url, description, tags, created_at, updated_at)
            VALUES (?, ?, '', '', '[]', ?, ?)
            """,
            ("role-b", "角色B", "2026-03-18T09:00:00+00:00", "2026-03-18T09:00:00+00:00"),
        )

        videos = [
            ("video-alpha", "role-a", "alpha source.mp4", str(remix_file_a), "2026-03-18T09:00:00+00:00"),
            ("video-gamma", "role-a", "gamma source.mp4", str(remix_file_b), "2026-03-18T09:10:00+00:00"),
            ("video-beta", "role-b", "beta source.mp4", str(lip_sync_file), "2026-03-18T09:05:00+00:00"),
        ]
        for video_id, role_id, title, file_path, uploaded_at in videos:
            connection.execute(
                """
                INSERT INTO role_videos (
                    id, role_id, title, file_path, thumbnail_url, duration_sec, aspect_ratio,
                    is_pinned, uploaded_at, deleted_at, asr_status, asr_error_message
                ) VALUES (?, ?, ?, ?, '', 10, '16:9', 0, ?, NULL, 'success', NULL)
                """,
                (video_id, role_id, title, file_path, uploaded_at),
            )

        connection.execute(
            """
            INSERT INTO remix_tasks (
                id, role_id, source_video_id, task_batch_no, prompt_text, product_doc_url,
                target_count, is_max_mode, aspect_mode, resolution, subtitle_enabled, status,
                running_count, success_count, failed_count, created_at, finished_at, error_message
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, 0, 0, ?, NULL, NULL)
            """,
            (
                "remix-task-a",
                "role-a",
                "video-alpha",
                "batch-a",
                "prompt",
                "",
                1,
                0,
                "default",
                "720p",
                1,
                "success",
                "2026-03-18T09:01:00+00:00",
            ),
        )
        connection.execute(
            """
            INSERT INTO remix_tasks (
                id, role_id, source_video_id, task_batch_no, prompt_text, product_doc_url,
                target_count, is_max_mode, aspect_mode, resolution, subtitle_enabled, status,
                running_count, success_count, failed_count, created_at, finished_at, error_message
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, 0, 0, ?, NULL, NULL)
            """,
            (
                "remix-task-b",
                "role-a",
                "video-gamma",
                "batch-b",
                "prompt",
                "",
                1,
                0,
                "default",
                "720p",
                1,
                "success",
                "2026-03-18T09:11:00+00:00",
            ),
        )
        connection.execute(
            """
            INSERT INTO remix_tasks (
                id, role_id, source_video_id, task_batch_no, prompt_text, product_doc_url,
                target_count, is_max_mode, aspect_mode, resolution, subtitle_enabled, status,
                running_count, success_count, failed_count, created_at, finished_at, error_message
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, 0, 0, ?, NULL, NULL)
            """,
            (
                "remix-task-failed",
                "role-b",
                "video-beta",
                "batch-c",
                "prompt",
                "",
                1,
                0,
                "default",
                "720p",
                1,
                "failed",
                "2026-03-18T09:12:00+00:00",
            ),
        )
        connection.execute(
            """
            INSERT INTO remix_task_items (
                id, remix_task_id, segment_id, rewritten_text, tts_audio_path, output_video_url,
                status, error_message, created_at, finished_at, comfy_prompt_id
            ) VALUES (?, ?, ?, ?, ?, ?, ?, NULL, ?, NULL, ?)
            """,
            (
                "remix-item-a",
                "remix-task-a",
                "segment-a",
                "script-a",
                "/tmp/a.wav",
                "/tmp/a.mp4",
                "success",
                "2026-03-18T09:01:10+00:00",
                "prompt-a",
            ),
        )
        connection.execute(
            """
            INSERT INTO remix_task_items (
                id, remix_task_id, segment_id, rewritten_text, tts_audio_path, output_video_url,
                status, error_message, created_at, finished_at, comfy_prompt_id
            ) VALUES (?, ?, ?, ?, ?, ?, ?, NULL, ?, NULL, ?)
            """,
            (
                "remix-item-b",
                "remix-task-b",
                "segment-b",
                "script-b",
                "/tmp/b.wav",
                "/tmp/b.mp4",
                "success",
                "2026-03-18T09:11:10+00:00",
                "prompt-b",
            ),
        )
        connection.execute(
            """
            INSERT INTO remix_task_items (
                id, remix_task_id, segment_id, rewritten_text, tts_audio_path, output_video_url,
                status, error_message, created_at, finished_at, comfy_prompt_id
            ) VALUES (?, ?, ?, ?, ?, ?, ?, NULL, ?, NULL, ?)
            """,
            (
                "remix-item-failed",
                "remix-task-failed",
                "segment-c",
                "script-c",
                "/tmp/c.wav",
                "/tmp/c.mp4",
                "failed",
                "2026-03-18T09:12:10+00:00",
                "prompt-c",
            ),
        )

        connection.execute(
            """
            INSERT INTO lip_sync_tasks (
                id, project_id, role_id, base_video_id, selected_script_id, final_script_text,
                video_job_id, aspect_mode, resolution, subtitle_enabled, status, tts_audio_path,
                output_video_url, error_message, created_at, finished_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL, ?, NULL)
            """,
            (
                "lip-sync-task-success",
                "project-a",
                "role-b",
                "video-beta",
                "script-1",
                "hello",
                "job-1",
                "default",
                "720p",
                1,
                "success",
                "/tmp/lip.wav",
                "/tmp/lip.mp4",
                "2026-03-18T09:05:00+00:00",
            ),
        )
        connection.execute(
            """
            INSERT INTO lip_sync_tasks (
                id, project_id, role_id, base_video_id, selected_script_id, final_script_text,
                video_job_id, aspect_mode, resolution, subtitle_enabled, status, tts_audio_path,
                output_video_url, error_message, created_at, finished_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL, ?, NULL)
            """,
            (
                "lip-sync-task-failed",
                "project-b",
                "role-a",
                "video-alpha",
                "script-2",
                "hello",
                "job-2",
                "default",
                "720p",
                1,
                "failed",
                "/tmp/lip-failed.wav",
                "/tmp/lip-failed.mp4",
                "2026-03-18T09:13:00+00:00",
            ),
        )
        connection.commit()
    finally:
        connection.close()


@pytest.mark.anyio
async def test_final_videos_returns_only_success_results_and_filters(tmp_path, monkeypatch):
    monkeypatch.setenv("BS_MEDIA_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("BS_MEDIA_UPLOADS_DIR", str(tmp_path / "uploads"))
    monkeypatch.setenv("BS_MEDIA_DEFAULT_ASR_MODE", "mock")
    monkeypatch.setenv("BS_MEDIA_WORK_DIR", str(tmp_path / "work"))
    monkeypatch.setenv("BS_MEDIA_TEMP_DIR", str(tmp_path / "temp"))
    monkeypatch.setenv("BS_MEDIA_GENERATED_DIR", str(tmp_path / "generated"))

    async with app_client() as client:
        seed_final_video_rows(get_settings().database_path)

        response = await client.get("/api/final-videos")
        assert response.status_code == 200
        payload = response.json()
        assert len(payload["items"]) == 3
        assert [item["source_type"] for item in payload["items"]] == ["remix", "lip_sync", "remix"]
        assert [item["source_video_title"] for item in payload["items"]] == [
            "gamma source.mp4",
            "beta source.mp4",
            "alpha source.mp4",
        ]
        assert [item["summary_text"] for item in payload["items"]] == ["script-b", "hello", "script-a"]

        role_filtered = await client.get("/api/final-videos", params={"role_id": "role-a"})
        assert [item["role_id"] for item in role_filtered.json()["items"]] == ["role-a", "role-a"]

        search_filtered = await client.get("/api/final-videos", params={"q": "alpha"})
        assert [item["source_video_title"] for item in search_filtered.json()["items"]] == ["alpha source.mp4"]

        source_type_filtered = await client.get("/api/final-videos", params={"source_type": "lip_sync"})
        assert [item["source_type"] for item in source_type_filtered.json()["items"]] == ["lip_sync"]
        assert source_type_filtered.json()["items"][0]["source_video_title"] == "beta source.mp4"


@pytest.mark.anyio
async def test_final_videos_stream_returns_generated_file(tmp_path, monkeypatch):
    monkeypatch.setenv("BS_MEDIA_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("BS_MEDIA_UPLOADS_DIR", str(tmp_path / "uploads"))
    monkeypatch.setenv("BS_MEDIA_DEFAULT_ASR_MODE", "mock")
    monkeypatch.setenv("BS_MEDIA_WORK_DIR", str(tmp_path / "work"))
    monkeypatch.setenv("BS_MEDIA_TEMP_DIR", str(tmp_path / "temp"))
    monkeypatch.setenv("BS_MEDIA_GENERATED_DIR", str(tmp_path / "generated"))

    output_path = tmp_path / "generated" / "review-preview.mp4"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_bytes(b"fake-mp4")

    init_db(get_settings().database_path)
    connection = sqlite3.connect(get_settings().database_path)
    try:
        connection.execute(
            """
            INSERT INTO roles (id, name, avatar_url, description, tags, created_at, updated_at)
            VALUES ('role-stream', '角色流', '', '', '[]', '2026-03-18T09:00:00+00:00', '2026-03-18T09:00:00+00:00')
            """
        )
        connection.execute(
            """
            INSERT INTO role_videos (
                id, role_id, title, file_path, thumbnail_url, duration_sec, aspect_ratio,
                is_pinned, uploaded_at, deleted_at, asr_status, asr_error_message
            ) VALUES ('video-stream', 'role-stream', 'stream source.mp4', '/tmp/source.mp4', '', 10, '16:9', 0,
                      '2026-03-18T09:00:00+00:00', NULL, 'success', NULL)
            """
        )
        connection.execute(
            """
            INSERT INTO lip_sync_tasks (
                id, project_id, role_id, base_video_id, selected_script_id, final_script_text,
                video_job_id, aspect_mode, resolution, subtitle_enabled, status, tts_audio_path,
                output_video_url, error_message, created_at, finished_at
            ) VALUES (?, 'project-stream', 'role-stream', 'video-stream', 'script-stream', 'final text',
                      'job-stream', 'default', '720p', 1, 'success', '/tmp/audio.wav', ?, NULL,
                      '2026-03-18T09:05:00+00:00', NULL)
            """,
            ("lip-task-stream", str(output_path)),
        )
        connection.commit()
    finally:
        connection.close()

    async with app_client() as client:
        response = await client.get("/api/final-videos/lip_sync:lip-task-stream/stream", params={"source_type": "lip_sync"})

    assert response.status_code == 200
    assert response.content == b"fake-mp4"


@pytest.mark.anyio
async def test_final_videos_delete_hides_item_and_removes_file(tmp_path, monkeypatch):
    monkeypatch.setenv("BS_MEDIA_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("BS_MEDIA_UPLOADS_DIR", str(tmp_path / "uploads"))
    monkeypatch.setenv("BS_MEDIA_DEFAULT_ASR_MODE", "mock")
    monkeypatch.setenv("BS_MEDIA_WORK_DIR", str(tmp_path / "work"))
    monkeypatch.setenv("BS_MEDIA_TEMP_DIR", str(tmp_path / "temp"))
    monkeypatch.setenv("BS_MEDIA_GENERATED_DIR", str(tmp_path / "generated"))

    output_path = tmp_path / "generated" / "final-a.mp4"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_bytes(b"fake-final")

    init_db(get_settings().database_path)
    connection = sqlite3.connect(get_settings().database_path)
    try:
        connection.execute(
            """
            INSERT INTO roles (id, name, avatar_url, description, tags, created_at, updated_at)
            VALUES ('role-del', '角色删除', '', '', '[]', '2026-03-18T09:00:00+00:00', '2026-03-18T09:00:00+00:00')
            """
        )
        connection.execute(
            """
            INSERT INTO role_videos (
                id, role_id, title, file_path, thumbnail_url, duration_sec, aspect_ratio,
                is_pinned, uploaded_at, deleted_at, asr_status, asr_error_message
            ) VALUES ('video-del', 'role-del', 'source.mp4', '/tmp/source.mp4', '', 10, '16:9', 0,
                      '2026-03-18T09:00:00+00:00', NULL, 'success', NULL)
            """
        )
        connection.execute(
            """
            INSERT INTO remix_tasks (
                id, role_id, source_video_id, task_batch_no, prompt_text, product_doc_url,
                target_count, is_max_mode, aspect_mode, resolution, subtitle_enabled, status,
                running_count, success_count, failed_count, created_at, finished_at, error_message, deleted_at
            ) VALUES ('remix-task-del', 'role-del', 'video-del', 'batch-1', 'prompt', '', 1, 0, 'default', '720p', 1,
                      'success', 0, 1, 0, '2026-03-18T09:01:00+00:00', NULL, NULL, NULL)
            """
        )
        connection.execute(
            """
            INSERT INTO remix_task_items (
                id, remix_task_id, segment_id, comfy_prompt_id, rewritten_text, tts_audio_path, output_video_url,
                status, error_message, created_at, finished_at, final_deleted_at
            ) VALUES ('remix-item-del', 'remix-task-del', 'segment-x', 'prompt-x', 'script', '/tmp/x.wav', ?, 'success',
                      NULL, '2026-03-18T09:01:10+00:00', NULL, NULL)
            """,
            (str(output_path),),
        )
        connection.commit()
    finally:
        connection.close()

    async with app_client() as client:
        before = await client.get("/api/final-videos", params={"role_id": "role-del"})
        assert before.status_code == 200
        assert [item["id"] for item in before.json()["items"]] == ["remix:remix-item-del"]

        # 角色不匹配时必须拒绝
        wrong_role = await client.delete(
            "/api/final-videos/remix:remix-item-del",
            params={"role_id": "role-other", "source_type": "remix"},
        )
        assert wrong_role.status_code == 404

        deleted = await client.delete(
            "/api/final-videos/remix:remix-item-del",
            params={"role_id": "role-del", "source_type": "remix"},
        )
        assert deleted.status_code == 200

        after = await client.get("/api/final-videos", params={"role_id": "role-del"})
        assert after.status_code == 200
        assert after.json()["items"] == []

    assert not output_path.exists()


@pytest.mark.anyio
async def test_final_videos_batch_delete_returns_counts(tmp_path, monkeypatch):
    monkeypatch.setenv("BS_MEDIA_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("BS_MEDIA_UPLOADS_DIR", str(tmp_path / "uploads"))
    monkeypatch.setenv("BS_MEDIA_DEFAULT_ASR_MODE", "mock")
    monkeypatch.setenv("BS_MEDIA_WORK_DIR", str(tmp_path / "work"))
    monkeypatch.setenv("BS_MEDIA_TEMP_DIR", str(tmp_path / "temp"))
    monkeypatch.setenv("BS_MEDIA_GENERATED_DIR", str(tmp_path / "generated"))

    output_path = tmp_path / "generated" / "lip-final.mp4"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_bytes(b"fake-final")

    init_db(get_settings().database_path)
    connection = sqlite3.connect(get_settings().database_path)
    try:
        connection.execute(
            """
            INSERT INTO roles (id, name, avatar_url, description, tags, created_at, updated_at)
            VALUES ('role-batch', '角色批量', '', '', '[]', '2026-03-18T09:00:00+00:00', '2026-03-18T09:00:00+00:00')
            """
        )
        connection.execute(
            """
            INSERT INTO role_videos (
                id, role_id, title, file_path, thumbnail_url, duration_sec, aspect_ratio,
                is_pinned, uploaded_at, deleted_at, asr_status, asr_error_message
            ) VALUES ('video-batch', 'role-batch', 'source.mp4', '/tmp/source.mp4', '', 10, '16:9', 0,
                      '2026-03-18T09:00:00+00:00', NULL, 'success', NULL)
            """
        )
        connection.execute(
            """
            INSERT INTO lip_sync_tasks (
                id, project_id, role_id, base_video_id, selected_script_id, final_script_text,
                video_job_id, aspect_mode, resolution, subtitle_enabled, status, tts_audio_path,
                output_video_url, error_message, created_at, finished_at, deleted_at, final_deleted_at
            ) VALUES ('lip-batch', 'p', 'role-batch', 'video-batch', 's', 'hello', 'job', 'default', '720p', 1,
                      'success', '/tmp/a.wav', ?, NULL, '2026-03-18T09:01:00+00:00', NULL, NULL, NULL)
            """,
            (str(output_path),),
        )
        connection.commit()
    finally:
        connection.close()

    async with app_client() as client:
        payload = {
            "role_id": "role-batch",
            "items": [
                {"id": "lip_sync:lip-batch", "source_type": "lip_sync"},
                {"id": "remix:missing", "source_type": "remix"},
            ],
        }
        response = await client.post("/api/final-videos/batch-delete", json=payload)
        assert response.status_code == 200
        body = response.json()
        assert body["deleted_count"] == 1
        assert body["failed_count"] == 1

    assert not output_path.exists()
