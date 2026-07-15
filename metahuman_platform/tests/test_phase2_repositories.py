from platform_app.db import init_db
from platform_app.repositories.asr_repository import AsrRepository
from platform_app.repositories.preprocess_job_repository import PreprocessJobRepository
from platform_app.repositories.remix_repository import RemixSegmentRepository, RemixTaskRepository
from platform_app.repositories.review_repository import ReviewRecordRepository
from platform_app.repositories.role_repository import RoleRepository
from platform_app.repositories.smart_clip_repository import SmartClipRepository
from platform_app.repositories.video_repository import VideoRepository


def _prepare_role_video(db_path):
    role_repo = RoleRepository(db_path)
    video_repo = VideoRepository(db_path)
    asr_repo = AsrRepository(db_path)

    role = role_repo.create(name="测试角色", description="", tags=[], avatar_url="")
    video = video_repo.create(
        role_id=role["id"],
        title="sample.mp4",
        file_path="/tmp/sample.mp4",
        thumbnail_url="",
        duration_sec=18.0,
        aspect_ratio="16:9",
    )
    asr_repo.upsert(
        role_video_id=video["id"],
        full_text="第一句。第二句。",
        segments=[
            {"start_sec": 0.0, "end_sec": 8.0, "text": "第一句"},
            {"start_sec": 8.0, "end_sec": 16.0, "text": "第二句"},
        ],
    )
    return role, video


def test_phase2_repositories_support_jobs_segments_tasks_and_reviews(tmp_path):
    db_path = tmp_path / "app.db"
    init_db(db_path)
    role, video = _prepare_role_video(db_path)

    job_repo = PreprocessJobRepository(db_path)
    segment_repo = RemixSegmentRepository(db_path)
    task_repo = RemixTaskRepository(db_path)
    review_repo = ReviewRecordRepository(db_path)

    job = job_repo.create(role_video_id=video["id"], job_type="remix_preprocess")
    assert job["status"] == "pending"

    running = job_repo.update(job["id"], status="running", progress=40)
    assert running["status"] == "running"
    assert running["progress"] == 40

    segment_repo.replace_for_video(
        role_id=role["id"],
        source_video_id=video["id"],
        segments=[
            {
                "start_sec": 0.0,
                "end_sec": 8.0,
                "duration_sec": 8.0,
                "asr_text": "第一句",
                "segment_file_path": str(tmp_path / "clip-1.mp4"),
            },
            {
                "start_sec": 8.0,
                "end_sec": 16.0,
                "duration_sec": 8.0,
                "asr_text": "第二句",
                "segment_file_path": str(tmp_path / "clip-2.mp4"),
            },
        ],
    )
    segments = segment_repo.list_by_video(video["id"])
    assert len(segments) == 2

    task = task_repo.create_task(
        role_id=role["id"],
        source_video_id=video["id"],
        prompt_text="卖点提示",
        product_doc_url="",
        target_count=2,
        is_max_mode=False,
        aspect_mode="default",
        resolution="720p",
        subtitle_enabled=True,
        status="ready",
    )
    items = task_repo.create_items(
        remix_task_id=task["id"],
        segment_ids=[segment["id"] for segment in segments],
    )
    assert len(items) == 2

    first_item = task_repo.update_item(
        items[0]["id"],
        status="video_generating",
        comfy_prompt_id="prompt-001",
        rewritten_text="改写文案",
        tts_audio_path=str(tmp_path / "tts.wav"),
    )
    assert first_item["status"] == "video_generating"
    assert first_item["comfy_prompt_id"] == "prompt-001"

    first_item = task_repo.update_item(
        items[0]["id"],
        status="success",
        comfy_prompt_id="prompt-001",
        rewritten_text="改写文案",
        tts_audio_path=str(tmp_path / "tts.wav"),
        output_video_url=str(tmp_path / "result.mp4"),
    )
    assert first_item["status"] == "success"

    updated_task = task_repo.refresh_counts(task["id"])
    assert updated_task["success_count"] == 1

    review = review_repo.create(
        source_type="remix",
        source_task_id=items[0]["id"],
        status="pending_review",
        review_note="",
    )
    assert review["source_task_id"] == items[0]["id"]
    assert review["status"] == "pending_review"


def test_phase2_repositories_support_smart_clip_projects_segments_and_candidates(tmp_path):
    db_path = tmp_path / "app.db"
    init_db(db_path)
    role, video = _prepare_role_video(db_path)

    repo = SmartClipRepository(db_path)

    project = repo.create_project(
        role_id=role["id"],
        source_video_id=video["id"],
        source_video_title=video["title"],
        status="analyzing",
        stage="classifying",
    )
    assert project["status"] == "analyzing"
    assert project["stage"] == "classifying"
    assert project["export_current_index"] == 0

    stored_project = repo.get_project(project["id"])
    assert stored_project["source_video_id"] == video["id"]
    assert repo.list_projects_by_role(role["id"])[0]["id"] == project["id"]

    repo.replace_segments(
        project_id=project["id"],
        source_video_id=video["id"],
        segments=[
            {
                "id": "segment-1",
                "start_sec": 0.0,
                "end_sec": 18.0,
                "duration_sec": 18.0,
                "asr_text": "讲商品卖点",
                "classification": "sales",
                "keep_flag": True,
                "reason": "明确讲解商品",
            },
            {
                "id": "segment-2",
                "start_sec": 30.0,
                "end_sec": 42.0,
                "duration_sec": 12.0,
                "asr_text": "谢谢大家支持",
                "classification": "chat",
                "keep_flag": False,
                "reason": "感谢互动",
            },
        ],
    )
    segments = repo.list_segments(project["id"])
    assert len(segments) == 2
    assert segments[0]["classification"] == "sales"
    assert segments[0]["keep_flag"] is True
    assert segments[1]["keep_flag"] is False
    assert repo.get_candidate("missing-candidate") is None

    repo.replace_candidates(
        project_id=project["id"],
        candidates=[
            {
                "id": "candidate-1",
                "clip_index": 1,
                "title": "切片 1",
                "duration_sec": 56.0,
                "segment_refs_json": '["segment-1"]',
                "source_time_ranges_json": '[{"start_sec": 0.0, "end_sec": 18.0}]',
                "preview_text": "讲商品卖点",
                "status": "active",
            },
            {
                "id": "candidate-2",
                "clip_index": 2,
                "title": "切片 2",
                "duration_sec": 48.0,
                "segment_refs_json": '["segment-2"]',
                "source_time_ranges_json": '[{"start_sec": 30.0, "end_sec": 42.0}]',
                "preview_text": "感谢互动",
                "status": "active",
            },
        ],
    )
    candidates = repo.list_candidates(project["id"])
    assert len(candidates) == 2
    assert candidates[0]["clip_index"] == 1
    assert repo.get_candidate("candidate-1")["title"] == "切片 1"

    updated_project = repo.update_project_status(
        project["id"],
        status="ready",
        stage="building_candidates",
    )
    assert updated_project["status"] == "ready"
    assert updated_project["stage"] == "building_candidates"

    deleted = repo.soft_delete_candidate("candidate-2")
    assert deleted["status"] == "deleted"
    assert len(repo.list_candidates(project["id"])) == 1
    assert len(repo.list_candidates(project["id"], include_deleted=True)) == 2

    failed = repo.mark_candidate_failed("candidate-2", error_message="导出失败")
    assert failed["status"] == "failed"
    assert failed["error_message"] == "导出失败"
    assert failed["output_video_path"] is None

    retrying = repo.mark_candidate_exporting("candidate-2")
    assert retrying["status"] == "exporting"
    assert retrying["error_message"] is None
    assert retrying["output_video_path"] is None

    repo.update_project_progress(
        project["id"],
        stage="exporting",
        export_total_count=2,
        export_completed_count=1,
        export_current_index=2,
    )
    progress_project = repo.get_project(project["id"])
    assert progress_project["stage"] == "exporting"
    assert progress_project["export_total_count"] == 2
    assert progress_project["export_completed_count"] == 1
    assert progress_project["export_current_index"] == 2

    exporting = repo.mark_candidate_exporting("candidate-1")
    assert exporting["status"] == "exporting"
    exported = repo.mark_candidate_exported(
        "candidate-1",
        output_video_path=str(tmp_path / "candidate-1.mp4"),
    )
    assert exported["status"] == "exported"
    assert exported["error_message"] is None
    assert exported["output_video_path"].endswith("candidate-1.mp4")
    assert repo.list_projects_by_role(role["id"])[0]["status"] == "ready"
