from platform_app.db import init_db
from platform_app.repositories.asr_repository import AsrRepository
from platform_app.repositories.role_repository import RoleRepository
from platform_app.repositories.video_repository import VideoRepository


def test_video_repository_supports_pin_and_soft_delete(tmp_path):
    db_path = tmp_path / "app.db"
    init_db(db_path)

    role_repo = RoleRepository(db_path)
    video_repo = VideoRepository(db_path)
    asr_repo = AsrRepository(db_path)

    role = role_repo.create(
        name="测试角色",
        description="说明",
        tags=["带货", "美妆"],
        avatar_url="",
    )
    video = video_repo.create(
        role_id=role["id"],
        title="sample.mp4",
        file_path="/tmp/sample.mp4",
        thumbnail_url="",
        duration_sec=12.3,
        aspect_ratio="16:9",
    )

    pinned = video_repo.set_pinned(video["id"], True)
    assert pinned["is_pinned"] is True

    asr_repo.upsert(
        role_video_id=video["id"],
        full_text="测试文本",
        segments=[{"start_sec": 0.0, "end_sec": 12.3, "text": "测试文本"}],
    )
    assert video_repo.get(video["id"])["asr_status"] == "success"

    video_repo.soft_delete(video["id"])
    assert video_repo.get(video["id"]) is None
    assert video_repo.list_by_role(role["id"]) == []
