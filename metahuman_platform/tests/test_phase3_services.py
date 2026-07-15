from pathlib import Path

import pytest

from platform_app.db import init_db
from platform_app.repositories.asr_repository import AsrRepository
from platform_app.repositories.lip_sync_repository import (
    LipSyncProjectRepository,
    LipSyncTaskRepository,
    ScriptCandidateRepository,
)
from platform_app.repositories.review_repository import ReviewRecordRepository
from platform_app.repositories.role_repository import RoleRepository
from platform_app.repositories.video_repository import VideoRepository
from platform_app.services.lip_sync_generation_adapter import LipSyncGenerationAdapter
from platform_app.services.lip_sync_service import LipSyncService
from tests.fakes.algorithm_service_fakes import FakeLipSyncGenerationAdapter


class _CapturedBackgroundJob:
    def __init__(self, func, args, kwargs):
        self.func = func
        self.args = args
        self.kwargs = kwargs


def _make_background_capture(monkeypatch):
    jobs = []

    def fake_run_in_background(func, *args, **kwargs):
        jobs.append(_CapturedBackgroundJob(func, args, kwargs))
        return object()

    monkeypatch.setattr(
        "platform_app.services.lip_sync_service.run_in_background",
        fake_run_in_background,
        raising=False,
    )
    return jobs


def _prepare_context(tmp_path):
    db_path = tmp_path / "app.db"
    init_db(db_path)

    role_repo = RoleRepository(db_path)
    video_repo = VideoRepository(db_path)
    asr_repo = AsrRepository(db_path)

    role = role_repo.create(name="角色A", description="", tags=[], avatar_url="")
    video_dir = tmp_path / "uploads" / role["id"]
    video_dir.mkdir(parents=True, exist_ok=True)
    video_path = video_dir / "base.mp4"
    video_path.write_bytes(b"base video")
    video = video_repo.create(
        role_id=role["id"],
        title="base.mp4",
        file_path=str(video_path),
        thumbnail_url="",
        duration_sec=12.0,
        aspect_ratio="16:9",
    )
    asr_repo.upsert(
        role_video_id=video["id"],
        full_text="原始基础视频文案",
        segments=[{"start_sec": 0.0, "end_sec": 12.0, "text": "原始基础视频文案"}],
    )
    return db_path, role, video


def test_lip_sync_service_generates_candidates_and_uses_edited_script(tmp_path, monkeypatch):
    db_path, role, video = _prepare_context(tmp_path)
    service = LipSyncService(
        db_path=db_path,
        temp_dir=tmp_path / "temp",
        generated_dir=tmp_path / "generated",
        generation_adapter=FakeLipSyncGenerationAdapter(tmp_path / "temp", tmp_path / "generated"),
    )

    project = service.create_project(
        role_id=role["id"],
        base_video_id=video["id"],
        prompt_text="面膜补水",
        product_doc_path="补水商品文档",
    )
    generated = service.generate_candidates(project["id"], count=3)
    assert generated["project"]["status"] == "script_generated"
    assert len(generated["candidates"]) == 3

    updated = service.edit_candidate(generated["candidates"][0]["id"], edited_content="用户修改后文案")
    assert updated["edited_content"] == "用户修改后文案"
    selected = service.select_candidate(project["id"], generated["candidates"][0]["id"])
    assert selected["project"]["status"] == "script_selected"

    jobs = _make_background_capture(monkeypatch)
    task = service.create_task(
        project_id=project["id"],
        selected_script_id=generated["candidates"][0]["id"],
        aspect_mode="default",
        resolution="720p",
        subtitle_enabled=True,
    )
    assert task["status"] in {"starting", "video_generating"}
    assert len(jobs) == 1
    jobs[0].func(*jobs[0].args, **jobs[0].kwargs)

    detail = service.get_task_detail(task["id"])
    assert detail["task"]["final_script_text"] == "用户修改后文案"
    assert detail["task"]["status"] == "success"
    assert Path(detail["task"]["tts_audio_path"]).exists()
    assert Path(detail["task"]["output_video_url"]).exists()


def test_lip_sync_service_regenerates_similar_script(tmp_path):
    db_path, role, video = _prepare_context(tmp_path)
    service = LipSyncService(
        db_path=db_path,
        temp_dir=tmp_path / "temp",
        generated_dir=tmp_path / "generated",
        generation_adapter=FakeLipSyncGenerationAdapter(tmp_path / "temp", tmp_path / "generated"),
    )

    project = service.create_project(
        role_id=role["id"],
        base_video_id=video["id"],
        prompt_text="面膜补水",
        product_doc_path="补水商品文档",
    )
    generated = service.generate_candidates(project["id"], count=2)

    regenerated = service.regenerate_candidate(project["id"], generated["candidates"][0]["id"])
    assert regenerated["content"].startswith("面膜补水-类似一版-")
    refreshed = ScriptCandidateRepository(db_path).list_candidates(project["id"])
    assert len(refreshed) == 2
    assert refreshed[0]["id"] == generated["candidates"][0]["id"]
    assert refreshed[0]["content"] == regenerated["content"]


def test_lip_sync_service_regenerate_same_candidate_twice_replaces_in_place(tmp_path):
    db_path, role, video = _prepare_context(tmp_path)
    service = LipSyncService(
        db_path=db_path,
        temp_dir=tmp_path / "temp",
        generated_dir=tmp_path / "generated",
        generation_adapter=FakeLipSyncGenerationAdapter(tmp_path / "temp", tmp_path / "generated"),
    )

    project = service.create_project(
        role_id=role["id"],
        base_video_id=video["id"],
        prompt_text="面膜补水",
        product_doc_path="补水商品文档",
    )
    generated = service.generate_candidates(project["id"], count=2)

    first = service.regenerate_candidate(project["id"], generated["candidates"][0]["id"])
    second = service.regenerate_candidate(project["id"], generated["candidates"][0]["id"])

    refreshed = ScriptCandidateRepository(db_path).list_candidates(project["id"])
    assert len(refreshed) == 2
    assert refreshed[0]["id"] == generated["candidates"][0]["id"]
    assert refreshed[0]["content"] == second["content"]
    assert first["content"] != second["content"]


def test_lip_sync_service_blocks_tts_longer_than_30_seconds(tmp_path):
    db_path, role, video = _prepare_context(tmp_path)
    service = LipSyncService(
        db_path=db_path,
        temp_dir=tmp_path / "temp",
        generated_dir=tmp_path / "generated",
        generation_adapter=FakeLipSyncGenerationAdapter(
            tmp_path / "temp",
            tmp_path / "generated",
            estimated_duration=31.5,
        ),
    )

    project = service.create_project(
        role_id=role["id"],
        base_video_id=video["id"],
        prompt_text="面膜补水",
        product_doc_path="补水商品文档",
    )
    generated = service.generate_candidates(project["id"], count=1)
    service.select_candidate(project["id"], generated["candidates"][0]["id"])

    with pytest.raises(ValueError, match="TTS"):
        service.create_task(
            project_id=project["id"],
            selected_script_id=generated["candidates"][0]["id"],
            aspect_mode="default",
            resolution="720p",
            subtitle_enabled=True,
        )


def test_lip_sync_service_creates_pending_review_after_success(tmp_path, monkeypatch):
    db_path, role, video = _prepare_context(tmp_path)
    service = LipSyncService(
        db_path=db_path,
        temp_dir=tmp_path / "temp",
        generated_dir=tmp_path / "generated",
        generation_adapter=FakeLipSyncGenerationAdapter(tmp_path / "temp", tmp_path / "generated"),
    )

    project = service.create_project(
        role_id=role["id"],
        base_video_id=video["id"],
        prompt_text="面膜补水",
        product_doc_path="补水商品文档",
    )
    generated = service.generate_candidates(project["id"], count=1)
    service.select_candidate(project["id"], generated["candidates"][0]["id"])

    jobs = _make_background_capture(monkeypatch)
    task = service.create_task(
        project_id=project["id"],
        selected_script_id=generated["candidates"][0]["id"],
        aspect_mode="default",
        resolution="720p",
        subtitle_enabled=True,
    )
    assert task["status"] in {"starting", "video_generating"}
    assert len(jobs) == 1
    jobs[0].func(*jobs[0].args, **jobs[0].kwargs)
    detail = service.get_task_detail(task["id"])

    reviews = ReviewRecordRepository(db_path).list_pending()
    assert detail["task"]["status"] == "success"
    assert len(reviews) == 1
    assert reviews[0]["source_type"] == "lip_sync"
    assert reviews[0]["source_task_id"] == task["id"]


def test_lip_sync_service_cancel_task_does_not_block_queue(tmp_path, monkeypatch):
    db_path, role, video = _prepare_context(tmp_path)
    service = LipSyncService(
        db_path=db_path,
        temp_dir=tmp_path / "temp",
        generated_dir=tmp_path / "generated",
        generation_adapter=FakeLipSyncGenerationAdapter(tmp_path / "temp", tmp_path / "generated"),
    )

    project = service.create_project(
        role_id=role["id"],
        base_video_id=video["id"],
        prompt_text="面膜补水",
        product_doc_path="补水商品文档",
    )
    generated = service.generate_candidates(project["id"], count=1)
    service.select_candidate(project["id"], generated["candidates"][0]["id"])

    jobs = _make_background_capture(monkeypatch)
    task = service.create_task(
        project_id=project["id"],
        selected_script_id=generated["candidates"][0]["id"],
        aspect_mode="default",
        resolution="720p",
        subtitle_enabled=True,
    )
    assert len(jobs) == 1

    second = service.create_task(
        project_id=project["id"],
        selected_script_id=generated["candidates"][0]["id"],
        aspect_mode="default",
        resolution="720p",
        subtitle_enabled=True,
    )
    assert second["status"] == "queued"

    cancelled = service.cancel_task(second["id"])
    assert cancelled["status"] == "cancelled"
    jobs[0].func(*jobs[0].args, **jobs[0].kwargs)
    first_detail = service.get_task_detail(task["id"])
    assert first_detail["task"]["status"] == "success"
    assert LipSyncTaskRepository(db_path).get_task(second["id"])["status"] == "cancelled"
    assert LipSyncProjectRepository(db_path).get_project(project["id"])["status"] == "cancelled"


def test_lip_sync_service_get_task_detail_is_pure_read(tmp_path, monkeypatch):
    db_path, role, video = _prepare_context(tmp_path)
    service = LipSyncService(
        db_path=db_path,
        temp_dir=tmp_path / "temp",
        generated_dir=tmp_path / "generated",
        generation_adapter=FakeLipSyncGenerationAdapter(tmp_path / "temp", tmp_path / "generated"),
    )

    jobs = _make_background_capture(monkeypatch)

    project = service.create_project(
        role_id=role["id"],
        base_video_id=video["id"],
        prompt_text="面膜补水",
        product_doc_path="补水商品文档",
    )
    generated = service.generate_candidates(project["id"], count=1)
    service.select_candidate(project["id"], generated["candidates"][0]["id"])
    task = service.create_task(
        project_id=project["id"],
        selected_script_id=generated["candidates"][0]["id"],
        aspect_mode="default",
        resolution="720p",
        subtitle_enabled=True,
    )

    assert len(jobs) == 1
    before = service.task_repository.get_task(task["id"])["status"]
    detail = service.get_task_detail(task["id"])
    after = service.task_repository.get_task(task["id"])["status"]

    assert before == after
    assert detail["task"]["status"] == after
    assert len(jobs) == 1


def test_lip_sync_service_queue_then_auto_schedule_next_task(tmp_path, monkeypatch):
    db_path, role, video = _prepare_context(tmp_path)
    service = LipSyncService(
        db_path=db_path,
        temp_dir=tmp_path / "temp",
        generated_dir=tmp_path / "generated",
        generation_adapter=FakeLipSyncGenerationAdapter(tmp_path / "temp", tmp_path / "generated"),
    )

    jobs = _make_background_capture(monkeypatch)

    project = service.create_project(
        role_id=role["id"],
        base_video_id=video["id"],
        prompt_text="面膜补水",
        product_doc_path="补水商品文档",
    )
    generated = service.generate_candidates(project["id"], count=2)
    service.select_candidate(project["id"], generated["candidates"][0]["id"])

    first = service.create_task(
        project_id=project["id"],
        selected_script_id=generated["candidates"][0]["id"],
        aspect_mode="default",
        resolution="720p",
        subtitle_enabled=True,
    )
    second = service.create_task(
        project_id=project["id"],
        selected_script_id=generated["candidates"][1]["id"],
        aspect_mode="default",
        resolution="720p",
        subtitle_enabled=True,
    )

    assert first["status"] in {"starting", "video_generating"}
    assert second["status"] == "queued"
    assert len(jobs) == 1

    jobs[0].func(*jobs[0].args, **jobs[0].kwargs)
    assert len(jobs) >= 2
    assert service.task_repository.get_task(first["id"])["status"] == "success"
    assert service.task_repository.get_task(second["id"])["status"] in {"starting", "video_generating"}

    jobs[1].func(*jobs[1].args, **jobs[1].kwargs)
    assert service.task_repository.get_task(second["id"])["status"] == "success"


def test_lip_sync_adapter_uses_asr_context_for_duration_validation(tmp_path, monkeypatch):
    db_path, _, video = _prepare_context(tmp_path)
    called = {}

    def fake_validate_with_context(**kwargs):
        called.update(kwargs)
        return {
            "estimated_tts_duration_sec": 12.0,
            "valid": True,
        }

    monkeypatch.setattr(
        "platform_app.services.lip_sync_generation_adapter.validate_script_tts_duration_with_context",
        fake_validate_with_context,
    )

    adapter = LipSyncGenerationAdapter(
        db_path=db_path,
        temp_dir=tmp_path / "temp",
        generated_dir=tmp_path / "generated",
    )

    result = adapter.validate_script_tts_duration(
        base_video_path=video["file_path"],
        script_text="新的最终文案",
    )

    assert result["valid"] is True
    assert called["base_video_duration_sec"] == 12.0
    assert called["base_video_asr_text"] == "原始基础视频文案"
    assert called["script_text"] == "新的最终文案"


def test_lip_sync_adapter_poll_generation_returns_failed_on_empty_or_mismatched_job_id(tmp_path):
    db_path, _, _ = _prepare_context(tmp_path)
    adapter = LipSyncGenerationAdapter(
        db_path=db_path,
        temp_dir=tmp_path / "temp",
        generated_dir=tmp_path / "generated",
    )

    assert adapter.poll_generation(task_id="task-1", video_job_id="") == {
        "status": "failed",
        "message": "缺少有效的视频生成任务ID",
    }
    assert adapter.poll_generation(task_id="task-1", video_job_id="job-1") == {
        "status": "failed",
        "message": "任务与视频生成作业不匹配",
    }


def test_lip_sync_adapter_poll_generation_passes_task_output_dir(tmp_path, monkeypatch):
    db_path, _, _ = _prepare_context(tmp_path)
    captured = {}

    def fake_poll(**kwargs):
        captured.update(kwargs)
        return {"status": "pending"}

    monkeypatch.setattr(
        "platform_app.services.lip_sync_generation_adapter.pipeline_poll_lip_sync_generation",
        fake_poll,
    )

    adapter = LipSyncGenerationAdapter(
        db_path=db_path,
        temp_dir=tmp_path / "temp",
        generated_dir=tmp_path / "generated",
    )
    monkeypatch.setattr(
        adapter.task_repository,
        "get_task",
        lambda task_id: {"id": task_id, "video_job_id": "job-1"},
    )

    result = adapter.poll_generation(task_id="task-1", video_job_id="job-1")

    assert result == {"status": "pending"}
    assert captured["task_id"] == "task-1"
    assert captured["video_job_id"] == "job-1"
    assert captured["output_dir"] == str(
        (tmp_path / "generated" / "lip_sync" / "task-1" / "final").resolve()
    )
