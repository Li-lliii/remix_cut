from platform_app.db import init_db
from platform_app.repositories.asr_repository import AsrRepository
from platform_app.repositories.lip_sync_repository import (
    LipSyncProjectRepository,
    LipSyncTaskRepository,
    ScriptCandidateRepository,
)
from platform_app.repositories.role_repository import RoleRepository
from platform_app.repositories.video_repository import VideoRepository


def _prepare_role_video(db_path):
    role_repo = RoleRepository(db_path)
    video_repo = VideoRepository(db_path)
    asr_repo = AsrRepository(db_path)

    role = role_repo.create(name="测试角色", description="", tags=[], avatar_url="")
    video = video_repo.create(
        role_id=role["id"],
        title="base.mp4",
        file_path="/tmp/base.mp4",
        thumbnail_url="",
        duration_sec=12.0,
        aspect_ratio="16:9",
    )
    asr_repo.upsert(
        role_video_id=video["id"],
        full_text="基础视频原始文案",
        segments=[{"start_sec": 0.0, "end_sec": 12.0, "text": "基础视频原始文案"}],
    )
    return role, video


def test_lip_sync_repository_creates_project_candidates_and_task(tmp_path):
    db_path = tmp_path / "app.db"
    init_db(db_path)
    role, video = _prepare_role_video(db_path)

    project_repo = LipSyncProjectRepository(db_path)
    candidate_repo = ScriptCandidateRepository(db_path)
    task_repo = LipSyncTaskRepository(db_path)

    project = project_repo.create_project(
        role_id=role["id"],
        base_video_id=video["id"],
        prompt_text="补水面膜",
        product_doc_url="/tmp/product.txt",
        status="draft",
    )
    assert project["status"] == "draft"

    candidates = candidate_repo.replace_candidates(
        project_id=project["id"],
        candidates=[
            {
                "content": "候选文案一",
                "char_count": 5,
                "estimated_tts_duration_sec": 8.2,
            },
            {
                "content": "候选文案二",
                "char_count": 5,
                "estimated_tts_duration_sec": 9.1,
            },
            {
                "content": "候选文案三",
                "char_count": 5,
                "estimated_tts_duration_sec": 7.8,
            },
        ],
    )
    assert len(candidates) == 3

    selected = candidate_repo.update_candidate(
        candidates[0]["id"],
        is_selected=True,
        edited_content="用户最终文案",
        is_edited=True,
    )
    assert selected["is_selected"] is True
    assert selected["edited_content"] == "用户最终文案"

    next_selected = candidate_repo.update_candidate(
        candidates[1]["id"],
        is_selected=True,
    )
    all_candidates = candidate_repo.list_candidates(project["id"])
    selected_ids = [item["id"] for item in all_candidates if item["is_selected"]]
    assert next_selected["is_selected"] is True
    assert selected_ids == [candidates[1]["id"]]

    task = task_repo.create_task(
        project_id=project["id"],
        role_id=role["id"],
        base_video_id=video["id"],
        selected_script_id=selected["id"],
        final_script_text="用户最终文案",
        aspect_mode="default",
        resolution="720p",
        subtitle_enabled=True,
        status="pending",
        video_job_id=None,
    )
    assert task["status"] == "pending"
    assert task["final_script_text"] == "用户最终文案"
    assert task["video_job_id"] is None
