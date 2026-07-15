from io import BytesIO
import sqlite3
import threading
from pathlib import Path

import anyio
import httpx
import pytest

from conftest import app_client


@pytest.mark.anyio
async def test_roles_api_returns_without_hanging(tmp_path, monkeypatch):
    monkeypatch.setenv("BS_MEDIA_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("BS_MEDIA_UPLOADS_DIR", str(tmp_path / "uploads"))
    monkeypatch.setenv("BS_MEDIA_DEFAULT_ASR_MODE", "mock")

    async with app_client() as client:
        with anyio.fail_after(1):
            response = await client.get("/api/roles")

    assert response.status_code == 200
    assert response.json() == {"items": []}


@pytest.mark.anyio
async def test_upload_video_creates_record_and_returns_pending_asr(tmp_path, monkeypatch):
    monkeypatch.setenv("BS_MEDIA_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("BS_MEDIA_UPLOADS_DIR", str(tmp_path / "uploads"))
    monkeypatch.setenv("BS_MEDIA_DEFAULT_ASR_MODE", "mock")

    async with app_client() as client:
        role = (
            await client.post(
                "/api/roles",
                json={"name": "角色A", "description": "", "tags": ["带货"]},
            )
        ).json()

        response = await client.post(
            f"/api/roles/{role['id']}/videos/upload",
            files={"video": ("demo.mp4", b"fake video", "video/mp4")},
        )

        assert response.status_code == 200
        payload = response.json()
        assert payload["asr_status"] == "pending"
        assert payload["id"]

        listed = (await client.get(f"/api/roles/{role['id']}/videos")).json()
        assert len(listed["items"]) == 1


@pytest.mark.anyio
async def test_upload_returns_immediately_even_when_asr_runs_slowly(tmp_path, monkeypatch):
    monkeypatch.setenv("BS_MEDIA_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("BS_MEDIA_UPLOADS_DIR", str(tmp_path / "uploads"))
    monkeypatch.setenv("BS_MEDIA_DEFAULT_ASR_MODE", "mock")

    started = threading.Event()
    release = threading.Event()

    def slow_process_video_asr(self, video_id: str):
        del self, video_id
        started.set()
        release.wait(timeout=1)
        return None

    monkeypatch.setattr(
        "platform_app.services.video_service.VideoService.process_video_asr",
        slow_process_video_asr,
    )

    async with app_client() as client:
        role = (
            await client.post(
                "/api/roles",
                json={"name": "角色A", "description": "", "tags": ["带货"]},
            )
        ).json()

        with anyio.fail_after(0.2):
            response = await client.post(
                f"/api/roles/{role['id']}/videos/upload",
                files={"video": ("demo.mp4", b"fake video", "video/mp4")},
            )

        release.set()
        await anyio.sleep(0.05)

    assert response.status_code == 200
    assert started.is_set() is True


@pytest.mark.anyio
async def test_upload_failure_returns_error_and_does_not_create_record(tmp_path, monkeypatch):
    monkeypatch.setenv("BS_MEDIA_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("BS_MEDIA_UPLOADS_DIR", str(tmp_path / "uploads"))

    async with app_client() as client:
        role = (
            await client.post(
                "/api/roles",
                json={"name": "角色A", "description": "", "tags": []},
            )
        ).json()

        response = await client.post(f"/api/roles/{role['id']}/videos/upload", files={})

        assert response.status_code == 422
        payload = response.json()
        assert payload["error"]["code"]

        listed = (await client.get(f"/api/roles/{role['id']}/videos")).json()
        assert listed["items"] == []


@pytest.mark.anyio
async def test_upload_video_uses_service_mode_for_asr(tmp_path, monkeypatch):
    monkeypatch.setenv("BS_MEDIA_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("BS_MEDIA_UPLOADS_DIR", str(tmp_path / "uploads"))
    monkeypatch.setenv("BS_MEDIA_ASR_MODE", "service")
    monkeypatch.setenv("BS_MEDIA_ASR_SERVICE_BASE_URL", "http://asr.local")

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/transcribe"
        payload = request.read().decode("utf-8")
        assert "video_path" in payload
        return httpx.Response(
            200,
            json={
                "full_text": "服务识别结果",
                "segments": [{"start_sec": 0.0, "end_sec": 1.0, "text": "服务识别结果"}],
            },
        )

    monkeypatch.setattr(
        "platform_app.api.videos.AsrAdapter",
        lambda mode, **kwargs: __import__("platform_app.services.asr_adapter", fromlist=["AsrAdapter"]).AsrAdapter(
            mode,
            transport=httpx.MockTransport(handler),
            **kwargs,
        ),
    )

    async with app_client() as client:
        role = (
            await client.post(
                "/api/roles",
                json={"name": "角色A", "description": "", "tags": ["带货"]},
            )
        ).json()

        response = await client.post(
            f"/api/roles/{role['id']}/videos/upload",
            files={"video": ("demo.mp4", b"fake video", "video/mp4")},
        )

        assert response.status_code == 200
        payload = response.json()
        assert payload["asr_status"] == "pending"


@pytest.mark.anyio
async def test_role_cover_upload_and_fetch(tmp_path, monkeypatch):
    monkeypatch.setenv("BS_MEDIA_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("BS_MEDIA_UPLOADS_DIR", str(tmp_path / "uploads"))
    monkeypatch.setenv("BS_MEDIA_DEFAULT_ASR_MODE", "mock")

    async with app_client() as client:
        role = (
            await client.post(
                "/api/roles",
                json={"name": "角色封面测试", "description": "", "tags": []},
            )
        ).json()

        upload = await client.post(
            f"/api/roles/{role['id']}/cover",
            files={"cover": ("cover.png", b"fake image bytes", "image/png")},
        )

        assert upload.status_code == 200
        updated = upload.json()
        assert updated["avatar_url"]
        assert updated["updated_at"]

        fetched = await client.get(f"/api/roles/{role['id']}/cover")
        assert fetched.status_code == 200
        assert fetched.headers["content-type"].startswith("image/")


@pytest.mark.anyio
async def test_role_cover_upload_prefers_mime_over_filename_suffix(tmp_path, monkeypatch):
    monkeypatch.setenv("BS_MEDIA_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("BS_MEDIA_UPLOADS_DIR", str(tmp_path / "uploads"))
    monkeypatch.setenv("BS_MEDIA_DEFAULT_ASR_MODE", "mock")

    async with app_client() as client:
        role = (
            await client.post(
                "/api/roles",
                json={"name": "角色封面测试", "description": "", "tags": []},
            )
        ).json()

        upload = await client.post(
            f"/api/roles/{role['id']}/cover",
            files={"cover": ("cover.jpg", b"fake image bytes", "image/png")},
        )

        assert upload.status_code == 200
        fetched = await client.get(f"/api/roles/{role['id']}/cover")
        assert fetched.status_code == 200
        assert fetched.headers["content-type"].startswith("image/png")


@pytest.mark.anyio
async def test_role_cover_upload_rejects_invalid_inputs(tmp_path, monkeypatch):
    monkeypatch.setenv("BS_MEDIA_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("BS_MEDIA_UPLOADS_DIR", str(tmp_path / "uploads"))
    monkeypatch.setenv("BS_MEDIA_DEFAULT_ASR_MODE", "mock")

    async with app_client() as client:
        missing_role = await client.post(
            "/api/roles/not-exists/cover",
            files={"cover": ("cover.png", b"fake image bytes", "image/png")},
        )
        assert missing_role.status_code == 404

        role = (
            await client.post(
                "/api/roles",
                json={"name": "角色封面测试", "description": "", "tags": []},
            )
        ).json()

        empty_file = await client.post(
            f"/api/roles/{role['id']}/cover",
            files={"cover": ("cover.png", b"", "image/png")},
        )
        assert empty_file.status_code == 400

        invalid_mime = await client.post(
            f"/api/roles/{role['id']}/cover",
            files={"cover": ("cover.txt", b"fake image bytes", "text/plain")},
        )
        assert invalid_mime.status_code == 400


@pytest.mark.anyio
async def test_delete_role_permanently_removes_role_related_records_and_files(tmp_path, monkeypatch):
    monkeypatch.setenv("BS_MEDIA_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("BS_MEDIA_UPLOADS_DIR", str(tmp_path / "uploads"))
    monkeypatch.setenv("BS_MEDIA_WORK_DIR", str(tmp_path / "work"))
    monkeypatch.setenv("BS_MEDIA_TEMP_DIR", str(tmp_path / "temp"))
    monkeypatch.setenv("BS_MEDIA_GENERATED_DIR", str(tmp_path / "generated"))
    monkeypatch.setenv("BS_MEDIA_DEFAULT_ASR_MODE", "mock")

    async with app_client() as client:
        role = (
            await client.post(
                "/api/roles",
                json={"name": "待删除角色", "description": "测试删除", "tags": ["测试"]},
            )
        ).json()

        upload = await client.post(
            f"/api/roles/{role['id']}/videos/upload",
            files={"video": ("demo.mp4", b"fake video", "video/mp4")},
        )
        assert upload.status_code == 200
        video = upload.json()

        cover_upload = await client.post(
            f"/api/roles/{role['id']}/cover",
            files={"cover": ("cover.png", b"fake image bytes", "image/png")},
        )
        assert cover_upload.status_code == 200

        video_file = Path(video["file_path"])
        role_dir = Path(tmp_path / "uploads" / "roles" / role["id"])
        cover_dir = role_dir / "cover"
        assert video_file.exists()
        assert cover_dir.exists()

        delete_response = await client.delete(f"/api/roles/{role['id']}")
        assert delete_response.status_code == 200
        assert delete_response.json() == {"success": True}

        roles_payload = await client.get("/api/roles")
        assert roles_payload.status_code == 200
        assert roles_payload.json()["items"] == []

        role_detail = await client.get(f"/api/roles/{role['id']}")
        assert role_detail.status_code == 404

        deleted_video = await client.get(f"/api/videos/{video['id']}/asr")
        assert deleted_video.status_code == 404

        deleted_cover = await client.get(f"/api/roles/{role['id']}/cover")
        assert deleted_cover.status_code == 404

        assert not role_dir.exists()


@pytest.mark.anyio
async def test_video_asr_returns_summary_text_and_summary_source(tmp_path, monkeypatch):
    monkeypatch.setenv("BS_MEDIA_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("BS_MEDIA_UPLOADS_DIR", str(tmp_path / "uploads"))
    monkeypatch.setenv("BS_MEDIA_DEFAULT_ASR_MODE", "mock")
    monkeypatch.setattr("platform_app.api.videos.run_in_background", lambda *args, **kwargs: None)

    async with app_client() as client:
        role = (
            await client.post(
                "/api/roles",
                json={"name": "语音转文字总结测试", "description": "", "tags": []},
            )
        ).json()

        video = (
            await client.post(
                f"/api/roles/{role['id']}/videos/upload",
                files={"video": ("demo.mp4", b"fake video", "video/mp4")},
            )
        ).json()

        connection = sqlite3.connect(tmp_path / "app.db")
        try:
            connection.execute(
                """
                INSERT INTO video_asr_results (
                    id, role_video_id, full_text, segments_json,
                    summary_text, summary_status, summary_error_message, summary_updated_at,
                    created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, datetime('now'), datetime('now'))
                """,
                (
                    "summary-success",
                    video["id"],
                    "原始识别文本",
                    "[]",
                    "这是已经写入数据库的总结内容",
                    "success",
                    None,
                    "2026-03-25T00:00:00",
                ),
            )
            connection.execute(
                "UPDATE role_videos SET asr_status = 'success', asr_error_message = NULL WHERE id = ?",
                (video["id"],),
            )
            connection.commit()
        finally:
            connection.close()

        payload = (await client.get(f"/api/videos/{video['id']}/asr")).json()
        assert payload["summary"] == "这是已经写入数据库的总结内容"
        assert payload["summary_source"] == "success"
        assert payload["summary_status"] == "success"


@pytest.mark.anyio
async def test_video_asr_reports_failed_summary_state(tmp_path, monkeypatch):
    monkeypatch.setenv("BS_MEDIA_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("BS_MEDIA_UPLOADS_DIR", str(tmp_path / "uploads"))
    monkeypatch.setenv("BS_MEDIA_DEFAULT_ASR_MODE", "mock")
    monkeypatch.setattr("platform_app.api.videos.run_in_background", lambda *args, **kwargs: None)

    async with app_client() as client:
        role = (
            await client.post(
                "/api/roles",
                json={"name": "语音转文字失败测试", "description": "", "tags": []},
            )
        ).json()

        video = (
            await client.post(
                f"/api/roles/{role['id']}/videos/upload",
                files={"video": ("demo.mp4", b"fake video", "video/mp4")},
            )
        ).json()

        connection = sqlite3.connect(tmp_path / "app.db")
        try:
            connection.execute(
                """
                INSERT INTO video_asr_results (
                    id, role_video_id, full_text, segments_json,
                    summary_text, summary_status, summary_error_message, summary_updated_at,
                    created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, datetime('now'), datetime('now'))
                """,
                (
                    "summary-failed",
                    video["id"],
                    "原始识别文本",
                    "[]",
                    "",
                    "failed",
                    "总结失败",
                    "2026-03-25T00:00:00",
                ),
            )
            connection.execute(
                "UPDATE role_videos SET asr_status = 'success', asr_error_message = NULL WHERE id = ?",
                (video["id"],),
            )
            connection.commit()
        finally:
            connection.close()

        payload = (await client.get(f"/api/videos/{video['id']}/asr")).json()
        assert payload["summary"] == ""
        assert payload["summary_source"] == "failed"
        assert payload["summary_status"] == "failed"


@pytest.mark.anyio
async def test_video_asr_reports_pending_summary_state_when_result_is_missing(tmp_path, monkeypatch):
    monkeypatch.setenv("BS_MEDIA_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("BS_MEDIA_UPLOADS_DIR", str(tmp_path / "uploads"))
    monkeypatch.setenv("BS_MEDIA_DEFAULT_ASR_MODE", "mock")
    monkeypatch.setattr("platform_app.api.videos.run_in_background", lambda *args, **kwargs: None)

    async with app_client() as client:
        role = (
            await client.post(
                "/api/roles",
                json={"name": "语音转文字待处理测试", "description": "", "tags": []},
            )
        ).json()

        video = (
            await client.post(
                f"/api/roles/{role['id']}/videos/upload",
                files={"video": ("demo.mp4", b"fake video", "video/mp4")},
            )
        ).json()

        payload = (await client.get(f"/api/videos/{video['id']}/asr")).json()
        assert payload["summary"] == ""
        assert payload["summary_source"] == "pending"
        assert payload["summary_status"] == "pending"


@pytest.mark.anyio
async def test_video_asr_reports_pending_summary_state_when_result_is_missing_and_asr_failed(
    tmp_path, monkeypatch
):
    monkeypatch.setenv("BS_MEDIA_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("BS_MEDIA_UPLOADS_DIR", str(tmp_path / "uploads"))
    monkeypatch.setenv("BS_MEDIA_DEFAULT_ASR_MODE", "mock")
    monkeypatch.setattr("platform_app.api.videos.run_in_background", lambda *args, **kwargs: None)

    async with app_client() as client:
        role = (
            await client.post(
                "/api/roles",
                json={"name": "语音转文字失败无结果测试", "description": "", "tags": []},
            )
        ).json()

        video = (
            await client.post(
                f"/api/roles/{role['id']}/videos/upload",
                files={"video": ("demo.mp4", b"fake video", "video/mp4")},
            )
        ).json()

        connection = sqlite3.connect(tmp_path / "app.db")
        try:
            connection.execute(
                "UPDATE role_videos SET asr_status = 'failed', asr_error_message = '识别失败' WHERE id = ?",
                (video["id"],),
            )
            connection.commit()
        finally:
            connection.close()

        payload = (await client.get(f"/api/videos/{video['id']}/asr")).json()
        assert payload["summary"] == ""
        assert payload["summary_source"] == "pending"
        assert payload["summary_status"] == "pending"
        assert payload["status"] == "failed"
