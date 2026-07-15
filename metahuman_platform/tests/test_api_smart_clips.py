from pathlib import Path

import pytest

from conftest import app_client
from platform_app.db import init_db
from platform_app.repositories.asr_repository import AsrRepository
from platform_app.repositories.role_repository import RoleRepository
from platform_app.repositories.smart_clip_repository import SmartClipRepository
from platform_app.repositories.video_repository import VideoRepository
from platform_app.services.smart_clip_service import SmartClipService
from platform_app.settings import get_settings


def _prepare_role_video_with_asr(db_path):
    role_repo = RoleRepository(db_path)
    video_repo = VideoRepository(db_path)
    asr_repo = AsrRepository(db_path)

    role = role_repo.create(name="智能切片角色", description="", tags=[], avatar_url="")
    video_dir = Path(db_path).parent / "uploads" / role["id"]
    video_dir.mkdir(parents=True, exist_ok=True)
    video_path = video_dir / "source.mp4"
    video_path.write_bytes(b"source video")
    video = video_repo.create(
        role_id=role["id"],
        title="source.mp4",
        file_path=str(video_path),
        thumbnail_url="",
        duration_sec=120.0,
        aspect_ratio="16:9",
    )
    asr_repo.upsert(
        role_video_id=video["id"],
        full_text="第一段卖点。第二段卖点。第三段卖点。",
        segments=[
            {"id": "seg-1", "start_sec": 0.0, "end_sec": 12.0, "text": "第一段卖点"},
            {"id": "seg-2", "start_sec": 12.0, "end_sec": 28.0, "text": "第二段卖点"},
            {"id": "seg-3", "start_sec": 28.0, "end_sec": 40.0, "text": "第三段卖点"},
        ],
    )
    return role, video


@pytest.mark.anyio
async def test_smart_clip_api_project_flow_and_stream(tmp_path, monkeypatch):
    monkeypatch.setenv("BS_MEDIA_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("BS_MEDIA_UPLOADS_DIR", str(tmp_path / "uploads"))
    monkeypatch.setenv("BS_MEDIA_WORK_DIR", str(tmp_path / "work"))
    monkeypatch.setenv("BS_MEDIA_TEMP_DIR", str(tmp_path / "temp"))
    monkeypatch.setenv("BS_MEDIA_GENERATED_DIR", str(tmp_path / "generated"))
    monkeypatch.setenv("BS_MEDIA_DEFAULT_ASR_MODE", "mock")

    init_db(get_settings().database_path)
    role, video = _prepare_role_video_with_asr(get_settings().database_path)

    def fake_classify(*, asr_segments, config_path=None):
        del config_path
        assert len(asr_segments) == 3
        return [
            {
                "id": "seg-1",
                "start_sec": 0.0,
                "end_sec": 12.0,
                "duration_sec": 12.0,
                "asr_text": "第一段卖点",
                "classification": "sales",
            },
            {
                "id": "seg-2",
                "start_sec": 12.0,
                "end_sec": 28.0,
                "duration_sec": 16.0,
                "asr_text": "第二段卖点",
                "classification": "sales",
            },
            {
                "id": "seg-3",
                "start_sec": 28.0,
                "end_sec": 40.0,
                "duration_sec": 12.0,
                "asr_text": "第三段卖点",
                "classification": "sales",
            },
        ]

    def fake_resolve(classified_segments):
        return [{**segment, "keep_flag": True} for segment in classified_segments]

    def fake_build(classified_segments, *, min_duration_sec=40.0, max_duration_sec=90.0, pause_gap_sec=5.0):
        del min_duration_sec, max_duration_sec, pause_gap_sec
        return [
            {
                "clip_index": 1,
                "duration_sec": 40.0,
                "segment_refs": ["seg-1", "seg-2"],
                "source_time_ranges": [
                    {"start_sec": 0.0, "end_sec": 12.0},
                    {"start_sec": 12.0, "end_sec": 28.0},
                ],
                "preview_text": "第一段卖点 第二段卖点",
            },
            {
                "clip_index": 2,
                "duration_sec": 12.0,
                "segment_refs": ["seg-3"],
                "source_time_ranges": [
                    {"start_sec": 28.0, "end_sec": 40.0},
                ],
                "preview_text": "第三段卖点",
            },
        ]

    def fake_cut_video_clip(*, video_path: str, start_sec: float, end_sec: float, output_path: str):
        path = Path(output_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(f"{start_sec}-{end_sec}", encoding="utf-8")
        return str(path)

    def fake_concat_video_clips(*, clip_paths: list[str], output_path: str):
        path = Path(output_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("|".join(Path(item).read_text(encoding="utf-8") for item in clip_paths), encoding="utf-8")
        return str(path)

    background_calls = []

    def fake_run_in_background(func, *args, **kwargs):
        background_calls.append((getattr(func, "__name__", repr(func)), args, kwargs))
        return None

    monkeypatch.setattr("platform_app.api.smart_clips.run_in_background", fake_run_in_background)
    monkeypatch.setattr("platform_app.services.smart_clip_service.classify_sales_segments_with_llm", fake_classify)
    monkeypatch.setattr("platform_app.services.smart_clip_service.resolve_bridge_segments", fake_resolve)
    monkeypatch.setattr("platform_app.services.smart_clip_service.build_sales_clip_candidates", fake_build)
    monkeypatch.setattr("platform_app.services.smart_clip_service.cut_video_clip", fake_cut_video_clip)
    monkeypatch.setattr("platform_app.services.smart_clip_service.concat_video_clips", fake_concat_video_clips)
    service = SmartClipService(
        db_path=get_settings().database_path,
        temp_dir=tmp_path / "temp",
        generated_dir=tmp_path / "generated",
    )

    async with app_client() as client:
        create_response = await client.post(
            "/api/remix/smart-clips/projects",
            json={"role_id": role["id"], "source_video_id": video["id"]},
        )
        assert create_response.status_code == 200
        create_payload = create_response.json()
        assert create_payload["project"]["status"] == "analyzing"
        assert background_calls[0][0] == "process_project"
        project_id = create_payload["project"]["id"]

        service.process_project(project_id)
        detail_response = await client.get(f"/api/remix/smart-clips/projects/{project_id}")
        assert detail_response.status_code == 200
        detail_payload = detail_response.json()
        assert detail_payload["project"]["status"] == "ready"
        assert len(detail_payload["candidates"]) == 2

        list_response = await client.get(f"/api/remix/smart-clips/projects/{project_id}/candidates")
        assert list_response.status_code == 200
        assert len(list_response.json()["items"]) == 2
        ready_candidate_id = list_response.json()["items"][0]["id"]

        before_export_stream = await client.get(
            f"/api/remix/smart-clips/projects/{project_id}/candidates/{ready_candidate_id}/stream"
        )
        assert before_export_stream.status_code == 200
        assert before_export_stream.content == b"0.0-12.0|12.0-28.0"

        repo = SmartClipRepository(get_settings().database_path)
        deleted_candidate_id = list_response.json()["items"][1]["id"]
        deleted_response = await client.delete(f"/api/remix/smart-clips/candidates/{deleted_candidate_id}")
        assert deleted_response.status_code == 200
        assert deleted_response.json()["status"] == "deleted"

        export_response = await client.post(f"/api/remix/smart-clips/projects/{project_id}/export")
        assert export_response.status_code == 200
        assert export_response.json()["project"]["status"] == "exporting"
        assert background_calls[-1][0] == "export_project"

        service.export_project(project_id, assume_started=True)

        final_detail = await client.get(f"/api/remix/smart-clips/projects/{project_id}")
        assert final_detail.status_code == 200
        final_payload = final_detail.json()
        assert final_payload["project"]["status"] == "success"
        assert final_payload["project"]["stage"] == "exported"
        assert final_payload["project"]["export_total_count"] == 1
        assert final_payload["project"]["export_current_index"] == 1
        assert final_payload["project"]["export_completed_count"] == 1

        exported_candidates = final_payload["candidates"]
        assert len(exported_candidates) == 1
        exported_candidate = exported_candidates[0]
        assert exported_candidate["status"] == "exported"
        assert exported_candidate["output_video_path"]

        stream_response = await client.get(
            f"/api/remix/smart-clips/projects/{project_id}/candidates/{exported_candidate['id']}/stream"
        )
        assert stream_response.status_code == 200
        assert stream_response.content == b"0.0-12.0|12.0-28.0"
        assert stream_response.headers["content-type"].startswith("video/")

        assert repo.get_candidate(deleted_candidate_id)["status"] == "deleted"


@pytest.mark.anyio
async def test_smart_clip_candidate_list_rejects_missing_project(tmp_path, monkeypatch):
    monkeypatch.setenv("BS_MEDIA_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("BS_MEDIA_UPLOADS_DIR", str(tmp_path / "uploads"))
    monkeypatch.setenv("BS_MEDIA_WORK_DIR", str(tmp_path / "work"))
    monkeypatch.setenv("BS_MEDIA_TEMP_DIR", str(tmp_path / "temp"))
    monkeypatch.setenv("BS_MEDIA_GENERATED_DIR", str(tmp_path / "generated"))
    monkeypatch.setenv("BS_MEDIA_DEFAULT_ASR_MODE", "mock")

    init_db(get_settings().database_path)

    async with app_client() as client:
        response = await client.get("/api/remix/smart-clips/projects/missing-project/candidates")

    assert response.status_code == 404
    assert "智能切片项目不存在" in response.text


@pytest.mark.anyio
async def test_smart_clip_api_force_recreate_reuses_active_project(tmp_path, monkeypatch):
    monkeypatch.setenv("BS_MEDIA_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("BS_MEDIA_UPLOADS_DIR", str(tmp_path / "uploads"))
    monkeypatch.setenv("BS_MEDIA_WORK_DIR", str(tmp_path / "work"))
    monkeypatch.setenv("BS_MEDIA_TEMP_DIR", str(tmp_path / "temp"))
    monkeypatch.setenv("BS_MEDIA_GENERATED_DIR", str(tmp_path / "generated"))
    monkeypatch.setenv("BS_MEDIA_DEFAULT_ASR_MODE", "mock")

    init_db(get_settings().database_path)
    role, video = _prepare_role_video_with_asr(get_settings().database_path)
    repo = SmartClipRepository(get_settings().database_path)
    project = repo.create_project(
        role_id=role["id"],
        source_video_id=video["id"],
        source_video_title=video["title"],
        status="ready",
        stage="ready",
    )
    repo.replace_segments(
        project_id=project["id"],
        source_video_id=video["id"],
        segments=[
            {
                "id": "seg-old",
                "start_sec": 0.0,
                "end_sec": 10.0,
                "duration_sec": 10.0,
                "asr_text": "旧结果",
                "classification": "sales",
                "keep_flag": True,
                "reason": "旧结果",
            }
        ],
    )
    repo.replace_candidates(
        project_id=project["id"],
        candidates=[
            {
                "id": "candidate-old",
                "clip_index": 1,
                "title": "旧切片",
                "duration_sec": 10.0,
                "segment_refs_json": '["seg-old"]',
                "source_time_ranges_json": '[{"start_sec": 0.0, "end_sec": 10.0}]',
                "preview_text": "旧结果",
                "status": "active",
            }
        ],
    )

    background_calls = []

    def fake_run_in_background(func, *args, **kwargs):
        background_calls.append((getattr(func, "__name__", repr(func)), args, kwargs))
        return None

    monkeypatch.setattr("platform_app.api.smart_clips.run_in_background", fake_run_in_background)

    async with app_client() as client:
        response = await client.post(
            "/api/remix/smart-clips/projects",
            json={"source_video_id": video["id"], "force_recreate": True},
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["project"]["id"] == project["id"]
    assert payload["project"]["status"] == "analyzing"
    assert payload["project"]["stage"] == "classifying"
    assert payload["segments"] == []
    assert payload["candidates"] == []
    assert background_calls == [("process_project", (project["id"],), {})]


@pytest.mark.anyio
async def test_smart_clip_delete_rejects_exported_candidate(tmp_path, monkeypatch):
    monkeypatch.setenv("BS_MEDIA_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("BS_MEDIA_UPLOADS_DIR", str(tmp_path / "uploads"))
    monkeypatch.setenv("BS_MEDIA_WORK_DIR", str(tmp_path / "work"))
    monkeypatch.setenv("BS_MEDIA_TEMP_DIR", str(tmp_path / "temp"))
    monkeypatch.setenv("BS_MEDIA_GENERATED_DIR", str(tmp_path / "generated"))
    monkeypatch.setenv("BS_MEDIA_DEFAULT_ASR_MODE", "mock")

    init_db(get_settings().database_path)
    role, video = _prepare_role_video_with_asr(get_settings().database_path)
    repo = SmartClipRepository(get_settings().database_path)
    project = repo.create_project(
        role_id=role["id"],
        source_video_id=video["id"],
        source_video_title=video["title"],
        status="success",
        stage="exported",
    )
    stored = repo.replace_candidates(
        project_id=project["id"],
        candidates=[
            {
                "clip_index": 1,
                "title": "切片 1",
                "duration_sec": 42.0,
                "segment_refs_json": '["seg-1"]',
                "source_time_ranges_json": '[{"start_sec": 0.0, "end_sec": 18.0}]',
                "preview_text": "第一段卖点",
                "status": "exported",
            }
        ],
    )
    exported_path = tmp_path / "generated" / "clip.mp4"
    exported_path.parent.mkdir(parents=True, exist_ok=True)
    exported_path.write_text("clip", encoding="utf-8")
    repo.mark_candidate_exported(stored[0]["id"], output_video_path=str(exported_path))

    async with app_client() as client:
        response = await client.delete(f"/api/remix/smart-clips/candidates/{stored[0]['id']}")

    assert response.status_code == 404
    assert "仅可删除未导出的候选切片" in response.text
