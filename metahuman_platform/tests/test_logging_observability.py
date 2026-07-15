import logging
from pathlib import Path

from platform_app.db import init_db
from platform_app.repositories.asr_repository import AsrRepository
from platform_app.repositories.role_repository import RoleRepository
from platform_app.repositories.video_repository import VideoRepository
from platform_app.services.background_runner import run_in_background
from platform_app.services.lip_sync_service import LipSyncService
from platform_app.services.preprocess_service import PreprocessService
from platform_app.services.remix_service import RemixService
from tests.fakes.algorithm_service_fakes import FakeGenerationAdapter, FakeLipSyncGenerationAdapter, FakePreprocessAdapter


def _prepare_role_video_asr(tmp_path: Path, *, title: str, duration_sec: float):
    db_path = tmp_path / "app.db"
    init_db(db_path)
    role_repo = RoleRepository(db_path)
    video_repo = VideoRepository(db_path)
    asr_repo = AsrRepository(db_path)

    role = role_repo.create(name="角色A", description="", tags=[], avatar_url="")
    video_dir = tmp_path / "uploads" / role["id"]
    video_dir.mkdir(parents=True, exist_ok=True)
    video_path = video_dir / title
    video_path.write_bytes(b"video")
    video = video_repo.create(
        role_id=role["id"],
        title=title,
        file_path=str(video_path),
        thumbnail_url="",
        duration_sec=duration_sec,
        aspect_ratio="16:9",
    )
    asr_repo.upsert(
        role_video_id=video["id"],
        full_text="第一句。第二句。",
        segments=[
            {"start_sec": 0.0, "end_sec": duration_sec / 2, "text": "第一句"},
            {"start_sec": duration_sec / 2, "end_sec": duration_sec, "text": "第二句"},
        ],
    )
    return db_path, role, video


def test_background_runner_logs_function_name_and_exception_context(caplog):
    caplog.set_level(logging.ERROR)

    def boom(task_id: str):
        raise RuntimeError(f"boom:{task_id}")

    thread = run_in_background(boom, "task-123")
    thread.join(timeout=2)

    assert any("后台任务执行失败" in record.getMessage() for record in caplog.records)
    assert any("boom" in record.getMessage() for record in caplog.records)
    assert any("task-123" in record.getMessage() for record in caplog.records)


def test_run_task_logs_stage_transitions_and_poll_heartbeat(tmp_path: Path, caplog):
    caplog.set_level(logging.INFO)

    db_path, role, video = _prepare_role_video_asr(tmp_path, title="source.mp4", duration_sec=24.0)
    preprocess = PreprocessService(
        db_path=db_path,
        temp_dir=tmp_path / "temp",
        work_dir=tmp_path / "work",
        preprocess_adapter=FakePreprocessAdapter(tmp_path / "work"),
    )
    generation = FakeGenerationAdapter(tmp_path / "temp", tmp_path / "generated")
    service = RemixService(
        db_path=db_path,
        temp_dir=tmp_path / "temp",
        generated_dir=tmp_path / "generated",
        preprocess_service=preprocess,
        generation_adapter=generation,
    )

    task = service.create_task(
        role_id=role["id"],
        source_video_id=video["id"],
        prompt_text="卖点提示",
        product_doc_path="",
        target_count=1,
        is_max_mode=False,
        aspect_mode="default",
        resolution="720p",
        subtitle_enabled=True,
    )

    service.run_task(task["id"], poll_interval_sec=0.01)

    stages = {getattr(record, "stage", None) for record in caplog.records}
    assert "remix_task_created" in stages
    assert "remix_submit_generation" in stages
    assert "remix_poll_pending" in stages
    assert "remix_poll_success" in stages
    assert "remix_task_finished" in stages


def test_preprocess_and_lip_sync_services_log_stage_boundaries(tmp_path: Path, caplog):
    caplog.set_level(logging.INFO)

    db_path, role, video = _prepare_role_video_asr(tmp_path, title="base.mp4", duration_sec=12.0)

    preprocess = PreprocessService(
        db_path=db_path,
        temp_dir=tmp_path / "temp",
        work_dir=tmp_path / "work",
        preprocess_adapter=FakePreprocessAdapter(tmp_path / "work"),
    )
    preprocess.ensure_preprocess(video["id"])

    lip_sync = LipSyncService(
        db_path=db_path,
        temp_dir=tmp_path / "temp",
        generated_dir=tmp_path / "generated",
        generation_adapter=FakeLipSyncGenerationAdapter(tmp_path / "temp", tmp_path / "generated"),
    )
    project = lip_sync.create_project(
        role_id=role["id"],
        base_video_id=video["id"],
        prompt_text="面膜补水",
        product_doc_path="补水商品文档",
    )
    generated = lip_sync.generate_candidates(project["id"], count=2)
    task = lip_sync.create_task(
        project_id=project["id"],
        selected_script_id=generated["candidates"][0]["id"],
        aspect_mode="default",
        resolution="720p",
        subtitle_enabled=True,
    )
    lip_sync.get_task_detail(task["id"])
    lip_sync.get_task_detail(task["id"])

    stages = {getattr(record, "stage", None) for record in caplog.records}
    assert "preprocess_job_started" in stages
    assert "preprocess_job_success" in stages
    assert "lip_sync_project_created" in stages
    assert "lip_sync_candidates_generated" in stages
    assert "lip_sync_submit_generation" in stages
    assert "lip_sync_poll_pending" in stages
    assert "lip_sync_poll_success" in stages
