from pathlib import Path

from pathlib import Path

import pytest

from platform_app.db import init_db
from platform_app.repositories.asr_repository import AsrRepository
from platform_app.repositories.role_repository import RoleRepository
from platform_app.repositories.smart_clip_repository import SmartClipRepository
from platform_app.repositories.video_repository import VideoRepository
from platform_app.services.smart_clip_service import SmartClipService


def _prepare_role_video_with_asr(db_path, *, asr_status: str = "success"):
    role_repo = RoleRepository(db_path)
    video_repo = VideoRepository(db_path)
    asr_repo = AsrRepository(db_path)

    role = role_repo.create(name="测试角色", description="", tags=[], avatar_url="")
    video = video_repo.create(
        role_id=role["id"],
        title="source.mp4",
        file_path="/tmp/source.mp4",
        thumbnail_url="",
        duration_sec=120.0,
        aspect_ratio="16:9",
    )

    if asr_status == "success":
        asr_repo.upsert(
            role_video_id=video["id"],
            full_text="第一段卖点。第二段卖点。第三段闲聊。",
            segments=[
                {"id": "seg-1", "start_sec": 0.0, "end_sec": 18.0, "text": "第一段卖点"},
                {"id": "seg-2", "start_sec": 18.0, "end_sec": 42.0, "text": "第二段卖点"},
                {"id": "seg-3", "start_sec": 42.0, "end_sec": 56.0, "text": "第三段闲聊"},
            ],
        )
    else:
        video_repo.update_asr_status(video["id"], asr_status)

    return role, video


def test_create_project_requires_successful_asr(tmp_path):
    db_path = tmp_path / "app.db"
    init_db(db_path)
    role, video = _prepare_role_video_with_asr(db_path, asr_status="running")

    service = SmartClipService(db_path=db_path)

    with pytest.raises(ValueError, match="ASR"):
        service.create_project(role_id=role["id"], source_video_id=video["id"])

    repo = SmartClipRepository(db_path)
    assert repo.list_projects_by_role(role["id"]) == []


def test_create_project_rejects_role_mismatch(tmp_path):
    db_path = tmp_path / "app.db"
    init_db(db_path)
    role, video = _prepare_role_video_with_asr(db_path, asr_status="success")
    other_role_repo = RoleRepository(db_path)
    other_role = other_role_repo.create(name="其他角色", description="", tags=[], avatar_url="")

    service = SmartClipService(db_path=db_path)

    with pytest.raises(ValueError, match="不属于当前角色"):
        service.create_project(role_id=other_role["id"], source_video_id=video["id"])

    assert SmartClipRepository(db_path).list_projects_by_role(other_role["id"]) == []


def test_create_project_sets_status_to_analyzing(tmp_path):
    db_path = tmp_path / "app.db"
    init_db(db_path)
    role, video = _prepare_role_video_with_asr(db_path, asr_status="success")

    service = SmartClipService(db_path=db_path)
    project = service.create_project(role_id=role["id"], source_video_id=video["id"])

    assert project["status"] == "analyzing"
    assert project["stage"] == "classifying"
    assert project["source_video_id"] == video["id"]
    stored = SmartClipRepository(db_path).get_project(project["id"])
    assert stored["status"] == "analyzing"
    assert stored["source_video_title"] == video["title"]


def test_create_or_restart_project_force_recreate_reuses_active_project_and_resets_state(tmp_path):
    db_path = tmp_path / "app.db"
    init_db(db_path)
    role, video = _prepare_role_video_with_asr(db_path, asr_status="success")
    service = SmartClipService(
        db_path=db_path,
        temp_dir=tmp_path / "temp",
        generated_dir=tmp_path / "generated",
    )
    project = service.create_project(role_id=role["id"], source_video_id=video["id"])
    repo = SmartClipRepository(db_path)
    repo.replace_segments(
        project_id=project["id"],
        source_video_id=video["id"],
        segments=[
            {
                "id": "seg-old",
                "start_sec": 0.0,
                "end_sec": 18.0,
                "duration_sec": 18.0,
                "asr_text": "旧卖点",
                "classification": "sales",
                "keep_flag": True,
                "reason": "旧结果",
            }
        ],
    )
    stored_candidates = repo.replace_candidates(
        project_id=project["id"],
        candidates=[
            {
                "id": "candidate-old",
                "clip_index": 1,
                "title": "旧切片",
                "duration_sec": 42.0,
                "segment_refs_json": '["seg-old"]',
                "source_time_ranges_json": '[{"start_sec": 0.0, "end_sec": 18.0}]',
                "preview_text": "旧卖点",
                "status": "active",
            }
        ],
    )
    export_dir = tmp_path / "generated" / "smart_clips" / project["id"]
    temp_dir = tmp_path / "temp" / "smart_clips" / project["id"]
    export_dir.mkdir(parents=True, exist_ok=True)
    temp_dir.mkdir(parents=True, exist_ok=True)
    (export_dir / "old-preview.mp4").write_text("preview", encoding="utf-8")
    (temp_dir / "part-01.mp4").write_text("temp", encoding="utf-8")
    repo.update_project_progress(
        project["id"],
        stage="ready",
        total_asr_segments=30,
        kept_sales_segments=10,
        candidate_clip_count=1,
        export_total_count=1,
        export_completed_count=1,
        export_current_index=1,
    )
    repo.update_project_status(
        project["id"],
        status="ready",
        stage="ready",
        error_message="旧错误",
    )

    restarted, should_process = service.create_or_restart_project(
        role_id=role["id"],
        source_video_id=video["id"],
        force_recreate=True,
    )

    assert should_process is True
    assert restarted["id"] == project["id"]
    assert restarted["status"] == "analyzing"
    assert restarted["stage"] == "classifying"
    assert restarted["error_message"] is None
    assert restarted["total_asr_segments"] == 0
    assert restarted["kept_sales_segments"] == 0
    assert restarted["candidate_clip_count"] == 0
    assert restarted["export_total_count"] == 0
    assert restarted["export_completed_count"] == 0
    assert restarted["export_current_index"] == 0
    assert repo.list_segments(project["id"]) == []
    assert repo.list_candidates(project["id"], include_deleted=True) == []
    assert not export_dir.exists()
    assert not temp_dir.exists()


def test_process_project_writes_segments_and_candidates_and_marks_ready(tmp_path, monkeypatch):
    db_path = tmp_path / "app.db"
    init_db(db_path)
    role, video = _prepare_role_video_with_asr(db_path, asr_status="success")
    service = SmartClipService(db_path=db_path)
    project = service.create_project(role_id=role["id"], source_video_id=video["id"])

    captured = {}

    def fake_classify(*, asr_segments, config_path=None):
        captured["asr_segments"] = asr_segments
        return [
            {
                "id": "seg-1",
                "start_sec": 0.0,
                "end_sec": 18.0,
                "duration_sec": 18.0,
                "asr_text": "第一段卖点",
                "classification": "sales",
            },
            {
                "id": "seg-2",
                "start_sec": 18.0,
                "end_sec": 42.0,
                "duration_sec": 24.0,
                "asr_text": "第二段卖点",
                "classification": "bridge",
            },
            {
                "id": "seg-3",
                "start_sec": 42.0,
                "end_sec": 56.0,
                "duration_sec": 14.0,
                "asr_text": "第三段闲聊",
                "classification": "chat",
            },
        ]

    def fake_resolve(classified_segments):
        return [
            {**classified_segments[0], "keep_flag": True, "reason": "保留"},
            {**classified_segments[1], "keep_flag": True, "reason": "保留"},
            {**classified_segments[2], "keep_flag": False, "reason": "剔除"},
        ]

    def fake_build(classified_segments, *, min_duration_sec=40.0, max_duration_sec=90.0, pause_gap_sec=5.0):
        assert classified_segments[0]["keep_flag"] is True
        assert min_duration_sec == 40.0
        return [
            {
                "clip_index": 1,
                "duration_sec": 42.0,
                "segment_refs": ["seg-1", "seg-2"],
                "source_time_ranges": [
                    {"start_sec": 0.0, "end_sec": 18.0},
                    {"start_sec": 18.0, "end_sec": 42.0},
                ],
                "preview_text": "第一段卖点 第二段卖点",
            }
        ]

    monkeypatch.setattr("platform_app.services.smart_clip_service.classify_sales_segments_with_llm", fake_classify)
    monkeypatch.setattr("platform_app.services.smart_clip_service.resolve_bridge_segments", fake_resolve)
    monkeypatch.setattr("platform_app.services.smart_clip_service.build_sales_clip_candidates", fake_build)
    monkeypatch.setattr(
        "platform_app.services.smart_clip_service.cut_video_clip",
        lambda *, video_path, start_sec, end_sec, output_path: str(
            (lambda path: (path.parent.mkdir(parents=True, exist_ok=True), path.write_bytes(b"preview"), str(path.resolve()))[-1])(Path(output_path))
        ),
    )
    monkeypatch.setattr(
        "platform_app.services.smart_clip_service.concat_video_clips",
        lambda *, clip_paths, output_path: str(
            (lambda path: (path.parent.mkdir(parents=True, exist_ok=True), path.write_bytes(b"preview"), str(path.resolve()))[-1])(Path(output_path))
        ),
    )

    result = service.process_project(project["id"])

    assert captured["asr_segments"] == [
        {"id": "seg-1", "start_sec": 0.0, "end_sec": 18.0, "text": "第一段卖点"},
        {"id": "seg-2", "start_sec": 18.0, "end_sec": 42.0, "text": "第二段卖点"},
        {"id": "seg-3", "start_sec": 42.0, "end_sec": 56.0, "text": "第三段闲聊"},
    ]
    assert result["project"]["status"] == "ready"
    assert result["project"]["candidate_clip_count"] == 1
    assert result["project"]["total_asr_segments"] == 3
    assert result["project"]["kept_sales_segments"] == 2

    repo = SmartClipRepository(db_path)
    segments = repo.list_segments(project["id"])
    candidates = service.list_candidates(project["id"])
    assert len(segments) == 3
    assert segments[0]["classification"] == "sales"
    assert segments[2]["keep_flag"] is False
    assert len(candidates) == 1
    assert candidates[0]["status"] == "active"
    assert candidates[0]["output_video_path"]
    assert candidates[0]["source_time_ranges"] == [
        {"start_sec": 0.0, "end_sec": 18.0},
        {"start_sec": 18.0, "end_sec": 42.0},
    ]

    detail = service.get_project_detail(project["id"])
    assert detail["project"]["status"] == "ready"
    assert detail["source_video"]["id"] == video["id"]
    assert detail["asr_result"]["full_text"].startswith("第一段卖点")
    assert detail["segments"][0]["classification"] == "sales"
    assert detail["candidates"][0]["segment_refs"] == ["seg-1", "seg-2"]


def test_process_project_marks_failed_when_analysis_raises(tmp_path, monkeypatch):
    db_path = tmp_path / "app.db"
    init_db(db_path)
    role, video = _prepare_role_video_with_asr(db_path, asr_status="success")
    service = SmartClipService(db_path=db_path)
    project = service.create_project(role_id=role["id"], source_video_id=video["id"])

    def boom(*args, **kwargs):
        raise RuntimeError("智能切片失败")

    monkeypatch.setattr("platform_app.services.smart_clip_service.classify_sales_segments_with_llm", boom)

    result = service.process_project(project["id"])

    assert result["project"]["status"] == "failed"
    assert "智能切片失败" in result["project"]["error_message"]
    stored = SmartClipRepository(db_path).get_project(project["id"])
    assert stored["status"] == "failed"
    assert stored["error_message"] == "智能切片失败"


def test_process_project_returns_failed_detail_when_source_video_deleted(tmp_path, monkeypatch):
    db_path = tmp_path / "app.db"
    init_db(db_path)
    role, video = _prepare_role_video_with_asr(db_path, asr_status="success")
    service = SmartClipService(db_path=db_path)
    project = service.create_project(role_id=role["id"], source_video_id=video["id"])
    VideoRepository(db_path).soft_delete(video["id"])

    def boom(*args, **kwargs):
        raise RuntimeError("智能切片失败")

    monkeypatch.setattr("platform_app.services.smart_clip_service.classify_sales_segments_with_llm", boom)

    result = service.process_project(project["id"])

    assert result["project"]["status"] == "failed"
    assert result["source_video"] is None
    assert result["asr_result"]["role_video_id"] == video["id"]
    assert result["project"]["error_message"] in {"源视频不存在", "智能切片失败"}


def test_delete_candidate_soft_deletes_item(tmp_path, monkeypatch):
    db_path = tmp_path / "app.db"
    init_db(db_path)
    role, video = _prepare_role_video_with_asr(db_path, asr_status="success")
    service = SmartClipService(db_path=db_path)
    project = service.create_project(role_id=role["id"], source_video_id=video["id"])

    monkeypatch.setattr(
        "platform_app.services.smart_clip_service.classify_sales_segments_with_llm",
        lambda *, asr_segments, config_path=None: [
            {
                "id": "seg-1",
                "start_sec": 0.0,
                "end_sec": 18.0,
                "duration_sec": 18.0,
                "asr_text": "第一段卖点",
                "classification": "sales",
            }
        ],
    )
    monkeypatch.setattr(
        "platform_app.services.smart_clip_service.resolve_bridge_segments",
        lambda classified_segments: [{**classified_segments[0], "keep_flag": True}],
    )
    monkeypatch.setattr(
        "platform_app.services.smart_clip_service.build_sales_clip_candidates",
        lambda classified_segments, **kwargs: [
            {
                "clip_index": 1,
                "duration_sec": 42.0,
                "segment_refs": ["seg-1"],
                "source_time_ranges": [{"start_sec": 0.0, "end_sec": 18.0}],
                "preview_text": "第一段卖点",
            }
        ],
    )
    monkeypatch.setattr(
        "platform_app.services.smart_clip_service.cut_video_clip",
        lambda *, video_path, start_sec, end_sec, output_path: str(Path(output_path).resolve()),
    )

    service.process_project(project["id"])
    candidates = service.list_candidates(project["id"])
    assert candidates[0]["source_time_ranges"] == [{"start_sec": 0.0, "end_sec": 18.0}]
    deleted = service.delete_candidate(candidates[0]["id"])

    assert deleted["status"] == "deleted"
    assert deleted["source_time_ranges"] == [{"start_sec": 0.0, "end_sec": 18.0}]
    assert service.list_candidates(project["id"]) == []


def test_export_project_only_exports_active_candidates_and_updates_progress(tmp_path, monkeypatch):
    db_path = tmp_path / "app.db"
    init_db(db_path)
    role, video = _prepare_role_video_with_asr(db_path, asr_status="success")
    service = SmartClipService(
        db_path=db_path,
        temp_dir=tmp_path / "temp",
        generated_dir=tmp_path / "generated",
    )
    project = service.create_project(role_id=role["id"], source_video_id=video["id"])

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
        assert len(classified_segments) == 3
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

    preview_cut_calls = []
    preview_concat_calls = []

    def fake_cut_video_clip(*, video_path: str, start_sec: float, end_sec: float, output_path: str):
        preview_cut_calls.append((video_path, start_sec, end_sec, output_path))
        path = Path(output_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(f"{start_sec}-{end_sec}", encoding="utf-8")
        return str(path)

    def fake_concat_video_clips(*, clip_paths: list[str], output_path: str):
        preview_concat_calls.append((list(clip_paths), output_path))
        path = Path(output_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("|".join(Path(item).read_text(encoding="utf-8") for item in clip_paths), encoding="utf-8")
        return str(path)

    monkeypatch.setattr("platform_app.services.smart_clip_service.classify_sales_segments_with_llm", fake_classify)
    monkeypatch.setattr("platform_app.services.smart_clip_service.resolve_bridge_segments", fake_resolve)
    monkeypatch.setattr("platform_app.services.smart_clip_service.build_sales_clip_candidates", fake_build)
    monkeypatch.setattr("platform_app.services.smart_clip_service.cut_video_clip", fake_cut_video_clip)
    monkeypatch.setattr("platform_app.services.smart_clip_service.concat_video_clips", fake_concat_video_clips)

    service.process_project(project["id"])
    repo = SmartClipRepository(db_path)
    candidates = repo.list_candidates(project["id"])
    assert len(candidates) == 2
    assert all(candidate["output_video_path"] for candidate in candidates)
    deleted_candidate = candidates[1]
    service.delete_candidate(deleted_candidate["id"])

    started = service.start_export(project["id"])
    assert started["project"]["status"] == "exporting"
    assert started["project"]["export_total_count"] == 1
    assert started["project"]["export_current_index"] == 0

    result = service.export_project(project["id"], assume_started=True)

    assert len(preview_cut_calls) == 3
    assert len(preview_concat_calls) == 1
    assert result["project"]["status"] == "success"
    assert result["project"]["stage"] == "exported"
    assert result["project"]["export_total_count"] == 1
    assert result["project"]["export_current_index"] == 1
    assert result["project"]["export_completed_count"] == 1
    exported_candidates = service.list_candidates(project["id"])
    assert len(exported_candidates) == 1
    assert exported_candidates[0]["status"] == "exported"
    assert Path(exported_candidates[0]["output_video_path"]).exists()
    assert service.get_candidate_stream_path(
        project_id=project["id"],
        candidate_id=exported_candidates[0]["id"],
    ).exists()
    assert repo.get_candidate(deleted_candidate["id"])["status"] == "deleted"


def test_export_project_marks_project_failed_when_concat_fails(tmp_path, monkeypatch):
    db_path = tmp_path / "app.db"
    init_db(db_path)
    role, video = _prepare_role_video_with_asr(db_path, asr_status="success")
    service = SmartClipService(
        db_path=db_path,
        temp_dir=tmp_path / "temp",
        generated_dir=tmp_path / "generated",
    )
    project = service.create_project(role_id=role["id"], source_video_id=video["id"])

    def fake_classify(*, asr_segments, config_path=None):
        del config_path
        return [
            {
                "id": "seg-1",
                "start_sec": 0.0,
                "end_sec": 20.0,
                "duration_sec": 20.0,
                "asr_text": "第一段卖点",
                "classification": "sales",
            },
            {
                "id": "seg-2",
                "start_sec": 20.0,
                "end_sec": 40.0,
                "duration_sec": 20.0,
                "asr_text": "第二段卖点",
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
                    {"start_sec": 0.0, "end_sec": 20.0},
                    {"start_sec": 20.0, "end_sec": 40.0},
                ],
                "preview_text": "第一段卖点 第二段卖点",
            }
        ]

    def fake_cut_video_clip(*, video_path: str, start_sec: float, end_sec: float, output_path: str):
        path = Path(output_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(f"{start_sec}-{end_sec}", encoding="utf-8")
        return str(path)

    def fake_concat_video_clips(*, clip_paths: list[str], output_path: str):
        raise RuntimeError("拼接失败")

    monkeypatch.setattr("platform_app.services.smart_clip_service.classify_sales_segments_with_llm", fake_classify)
    monkeypatch.setattr("platform_app.services.smart_clip_service.resolve_bridge_segments", fake_resolve)
    monkeypatch.setattr("platform_app.services.smart_clip_service.build_sales_clip_candidates", fake_build)
    monkeypatch.setattr("platform_app.services.smart_clip_service.cut_video_clip", fake_cut_video_clip)
    monkeypatch.setattr("platform_app.services.smart_clip_service.concat_video_clips", fake_concat_video_clips)

    result = service.process_project(project["id"])

    assert result["project"]["status"] == "failed"
    assert "拼接失败" in result["project"]["error_message"]
    candidate = SmartClipRepository(db_path).list_candidates(project["id"], include_deleted=True)[0]
    assert candidate["status"] == "failed"


def test_export_project_marks_failed_when_source_video_deleted_after_start(tmp_path, monkeypatch):
    db_path = tmp_path / "app.db"
    init_db(db_path)
    role, video = _prepare_role_video_with_asr(db_path, asr_status="success")
    service = SmartClipService(
        db_path=db_path,
        temp_dir=tmp_path / "temp",
        generated_dir=tmp_path / "generated",
    )
    project = service.create_project(role_id=role["id"], source_video_id=video["id"])

    monkeypatch.setattr(
        "platform_app.services.smart_clip_service.classify_sales_segments_with_llm",
        lambda *, asr_segments, config_path=None: [
            {
                "id": "seg-1",
                "start_sec": 0.0,
                "end_sec": 20.0,
                "duration_sec": 20.0,
                "asr_text": "第一段卖点",
                "classification": "sales",
            }
        ],
    )
    monkeypatch.setattr(
        "platform_app.services.smart_clip_service.resolve_bridge_segments",
        lambda classified_segments: [{**classified_segments[0], "keep_flag": True}],
    )
    monkeypatch.setattr(
        "platform_app.services.smart_clip_service.build_sales_clip_candidates",
        lambda classified_segments, **kwargs: [
            {
                "clip_index": 1,
                "duration_sec": 20.0,
                "segment_refs": ["seg-1"],
                "source_time_ranges": [{"start_sec": 0.0, "end_sec": 20.0}],
                "preview_text": "第一段卖点",
            }
        ],
    )
    monkeypatch.setattr(
        "platform_app.services.smart_clip_service.cut_video_clip",
        lambda *, video_path, start_sec, end_sec, output_path: str(Path(output_path).resolve()),
    )

    service.process_project(project["id"])
    service.start_export(project["id"])
    VideoRepository(db_path).soft_delete(video["id"])

    result = service.export_project(project["id"], assume_started=True)

    assert result["project"]["status"] == "failed"
    assert result["project"]["stage"] == "failed"
    assert result["project"]["error_message"] == "源视频不存在"
    assert result["source_video"] is None


def test_export_project_exports_only_active_candidates_and_updates_progress(tmp_path, monkeypatch):
    db_path = tmp_path / "app.db"
    init_db(db_path)
    role, video = _prepare_role_video_with_asr(db_path, asr_status="success")
    service = SmartClipService(
        db_path=db_path,
        temp_dir=tmp_path / "temp",
        generated_dir=tmp_path / "generated",
    )
    project = service.create_project(role_id=role["id"], source_video_id=video["id"])

    monkeypatch.setattr(
        "platform_app.services.smart_clip_service.classify_sales_segments_with_llm",
        lambda *, asr_segments, config_path=None: [
            {
                "id": "seg-1",
                "start_sec": 0.0,
                "end_sec": 20.0,
                "duration_sec": 20.0,
                "asr_text": "第一段卖点",
                "classification": "sales",
            },
            {
                "id": "seg-2",
                "start_sec": 30.0,
                "end_sec": 55.0,
                "duration_sec": 25.0,
                "asr_text": "第二段卖点",
                "classification": "sales",
            },
            {
                "id": "seg-3",
                "start_sec": 70.0,
                "end_sec": 95.0,
                "duration_sec": 25.0,
                "asr_text": "第三段卖点",
                "classification": "sales",
            },
        ],
    )
    monkeypatch.setattr(
        "platform_app.services.smart_clip_service.resolve_bridge_segments",
        lambda classified_segments: [{**segment, "keep_flag": True} for segment in classified_segments],
    )
    monkeypatch.setattr(
        "platform_app.services.smart_clip_service.build_sales_clip_candidates",
        lambda classified_segments, **kwargs: [
            {
                "clip_index": 1,
                "duration_sec": 45.0,
                "segment_refs": ["seg-1", "seg-2"],
                "source_time_ranges": [
                    {"start_sec": 0.0, "end_sec": 20.0},
                    {"start_sec": 30.0, "end_sec": 55.0},
                ],
                "preview_text": "第一段卖点 第二段卖点",
            },
            {
                "clip_index": 2,
                "duration_sec": 25.0,
                "segment_refs": ["seg-3"],
                "source_time_ranges": [{"start_sec": 70.0, "end_sec": 95.0}],
                "preview_text": "第三段卖点",
            },
        ],
    )
    def fake_preview_cut(*, video_path: str, start_sec: float, end_sec: float, output_path: str):
        del video_path, start_sec, end_sec
        path = Path(output_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"preview")
        return str(path.resolve())

    def fake_preview_concat(*, clip_paths, output_path: str):
        del clip_paths
        path = Path(output_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"preview")
        return str(path.resolve())

    monkeypatch.setattr("platform_app.services.smart_clip_service.cut_video_clip", fake_preview_cut)
    monkeypatch.setattr("platform_app.services.smart_clip_service.concat_video_clips", fake_preview_concat)

    service.process_project(project["id"])
    candidates = service.list_candidates(project["id"])
    service.delete_candidate(candidates[1]["id"])
    exported_outputs = []

    def fake_cut(*, video_path: str, start_sec: float, end_sec: float, output_path: str):
        del video_path, start_sec, end_sec
        path = Path(output_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(f"clip:{path.name}".encode("utf-8"))
        exported_outputs.append(str(path))
        return str(path)

    def fake_concat(*, clip_paths: list[str], output_path: str):
        path = Path(output_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("|".join(Path(item).name for item in clip_paths), encoding="utf-8")
        exported_outputs.append(str(path))
        return str(path)

    monkeypatch.setattr("platform_app.services.smart_clip_service.cut_video_clip", fake_cut)
    monkeypatch.setattr("platform_app.services.smart_clip_service.concat_video_clips", fake_concat)

    started = service.start_export(project["id"])
    result = service.export_project(project["id"], assume_started=True)

    assert started["project"]["status"] == "exporting"
    assert result["project"]["status"] == "success"
    assert result["project"]["export_total_count"] == 1
    assert result["project"]["export_completed_count"] == 1
    assert result["project"]["export_current_index"] == 1
    exported_candidates = result["candidates"]
    assert len(exported_candidates) == 1
    assert exported_candidates[0]["status"] == "exported"
    assert Path(exported_candidates[0]["output_video_path"]).exists()
    stored_deleted = SmartClipRepository(db_path).get_candidate(candidates[1]["id"])
    assert stored_deleted["status"] == "deleted"
    assert exported_outputs == []


def test_get_candidate_stream_path_returns_exported_file(tmp_path, monkeypatch):
    db_path = tmp_path / "app.db"
    init_db(db_path)
    role, video = _prepare_role_video_with_asr(db_path, asr_status="success")
    service = SmartClipService(
        db_path=db_path,
        temp_dir=tmp_path / "temp",
        generated_dir=tmp_path / "generated",
    )
    project = service.create_project(role_id=role["id"], source_video_id=video["id"])

    monkeypatch.setattr(
        "platform_app.services.smart_clip_service.classify_sales_segments_with_llm",
        lambda *, asr_segments, config_path=None: [
            {
                "id": "seg-1",
                "start_sec": 0.0,
                "end_sec": 18.0,
                "duration_sec": 18.0,
                "asr_text": "第一段卖点",
                "classification": "sales",
            }
        ],
    )
    monkeypatch.setattr(
        "platform_app.services.smart_clip_service.resolve_bridge_segments",
        lambda classified_segments: [{**classified_segments[0], "keep_flag": True}],
    )
    monkeypatch.setattr(
        "platform_app.services.smart_clip_service.build_sales_clip_candidates",
        lambda classified_segments, **kwargs: [
            {
                "clip_index": 1,
                "duration_sec": 18.0,
                "segment_refs": ["seg-1"],
                "source_time_ranges": [{"start_sec": 0.0, "end_sec": 18.0}],
                "preview_text": "第一段卖点",
            }
        ],
    )
    monkeypatch.setattr(
        "platform_app.services.smart_clip_service.cut_video_clip",
        lambda *, video_path, start_sec, end_sec, output_path: str(Path(output_path).resolve()),
    )

    service.process_project(project["id"])
    candidate = service.list_candidates(project["id"])[0]
    stream_path = service.get_candidate_stream_path(project_id=project["id"], candidate_id=candidate["id"])

    assert stream_path == Path(candidate["output_video_path"])


def test_delete_candidate_rejects_exported_item(tmp_path, monkeypatch):
    db_path = tmp_path / "app.db"
    init_db(db_path)
    role, video = _prepare_role_video_with_asr(db_path, asr_status="success")
    service = SmartClipService(
        db_path=db_path,
        temp_dir=tmp_path / "temp",
        generated_dir=tmp_path / "generated",
    )
    project = service.create_project(role_id=role["id"], source_video_id=video["id"])

    monkeypatch.setattr(
        "platform_app.services.smart_clip_service.classify_sales_segments_with_llm",
        lambda *, asr_segments, config_path=None: [
            {
                "id": "seg-1",
                "start_sec": 0.0,
                "end_sec": 18.0,
                "duration_sec": 18.0,
                "asr_text": "第一段卖点",
                "classification": "sales",
            }
        ],
    )
    monkeypatch.setattr(
        "platform_app.services.smart_clip_service.resolve_bridge_segments",
        lambda classified_segments: [{**classified_segments[0], "keep_flag": True}],
    )
    monkeypatch.setattr(
        "platform_app.services.smart_clip_service.build_sales_clip_candidates",
        lambda classified_segments, **kwargs: [
            {
                "clip_index": 1,
                "duration_sec": 42.0,
                "segment_refs": ["seg-1"],
                "source_time_ranges": [{"start_sec": 0.0, "end_sec": 18.0}],
                "preview_text": "第一段卖点",
            }
        ],
    )
    monkeypatch.setattr(
        "platform_app.services.smart_clip_service.cut_video_clip",
        lambda *, video_path, start_sec, end_sec, output_path: str((tmp_path / "generated" / "clip.mp4").resolve()),
    )

    service.process_project(project["id"])
    repo = SmartClipRepository(db_path)
    candidate = service.list_candidates(project["id"])[0]
    exported_path = tmp_path / "generated" / "clip.mp4"
    exported_path.parent.mkdir(parents=True, exist_ok=True)
    exported_path.write_text("clip", encoding="utf-8")
    repo.mark_candidate_exported(candidate["id"], output_video_path=str(exported_path))

    with pytest.raises(ValueError, match="仅可删除未导出的候选切片"):
        service.delete_candidate(candidate["id"])


def test_list_candidates_rejects_missing_project(tmp_path):
    db_path = tmp_path / "app.db"
    init_db(db_path)

    service = SmartClipService(db_path=db_path)

    with pytest.raises(ValueError, match="智能切片项目不存在"):
        service.list_candidates("missing-project")
