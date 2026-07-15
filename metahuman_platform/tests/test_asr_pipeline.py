from platform_app.db import init_db
from platform_app.services.asr_adapter import AsrAdapter
from platform_app.repositories.role_repository import RoleRepository
from platform_app.repositories.video_repository import VideoRepository
from platform_app.services.asr_adapter import AsrAdapterError
from platform_app.services.video_service import VideoService


class SuccessAdapter:
    def transcribe(self, *, video_path, device=None, segment_seconds=60):
        return {
            "full_text": "识别成功",
            "segments": [{"start_sec": 0.0, "end_sec": 8.0, "text": "识别成功"}],
        }


class FailedAdapter:
    def transcribe(self, *, video_path, device=None, segment_seconds=60):
        raise AsrAdapterError("适配器失败")


def test_asr_adapter_rejects_algorithm_mode(tmp_path):
    target = tmp_path / "demo.mp4"
    target.write_bytes(b"fake")

    adapter = AsrAdapter(mode="algorithm")

    try:
        adapter.transcribe(video_path=str(target), device="cpu", segment_seconds=30)
    except AsrAdapterError as exc:
        assert "不支持的 ASR 模式" in str(exc)
    else:
        raise AssertionError("algorithm 模式应被拒绝")


def test_process_video_asr_persists_structured_result(tmp_path, monkeypatch):
    db_path = tmp_path / "app.db"
    init_db(db_path)

    role_repo = RoleRepository(db_path)
    role = role_repo.create(name="角色", description="", tags=[], avatar_url="")
    video_repo = VideoRepository(db_path)
    video = video_repo.create(
        role_id=role["id"],
        title="demo.mp4",
        file_path=str(tmp_path / "demo.mp4"),
        thumbnail_url="",
        duration_sec=8.0,
        aspect_ratio="16:9",
    )

    monkeypatch.setattr(VideoService, "_generate_asr_summary", lambda self, full_text: "识别成功总结", raising=False)
    service = VideoService(db_path=db_path, asr_adapter=SuccessAdapter())

    result = service.process_video_asr(video["id"])

    assert result["full_text"] == "识别成功"
    assert result["summary_text"] == "识别成功总结"
    assert result["summary_status"] == "success"
    assert result["summary_error_message"] is None
    stored_video = video_repo.get(video["id"])
    assert stored_video["asr_status"] == "success"


def test_process_video_asr_marks_video_failed_when_adapter_raises(tmp_path):
    db_path = tmp_path / "app.db"
    init_db(db_path)

    role_repo = RoleRepository(db_path)
    role = role_repo.create(name="角色", description="", tags=[], avatar_url="")
    video_repo = VideoRepository(db_path)
    video = video_repo.create(
        role_id=role["id"],
        title="broken.mp4",
        file_path=str(tmp_path / "broken.mp4"),
        thumbnail_url="",
        duration_sec=3.0,
        aspect_ratio="16:9",
    )

    service = VideoService(db_path=db_path, asr_adapter=FailedAdapter())

    service.process_video_asr(video["id"])

    stored_video = video_repo.get(video["id"])
    assert stored_video["asr_status"] == "failed"
    assert stored_video["asr_error_message"] == "适配器失败"


def test_process_video_asr_marks_summary_failed_without_reverting_asr_success(tmp_path, monkeypatch):
    db_path = tmp_path / "app.db"
    init_db(db_path)

    role_repo = RoleRepository(db_path)
    role = role_repo.create(name="角色", description="", tags=[], avatar_url="")
    video_repo = VideoRepository(db_path)
    video = video_repo.create(
        role_id=role["id"],
        title="summary-failed.mp4",
        file_path=str(tmp_path / "summary-failed.mp4"),
        thumbnail_url="",
        duration_sec=12.0,
        aspect_ratio="16:9",
    )

    def fail_summary(self, full_text: str):
        raise RuntimeError("总结失败")

    monkeypatch.setattr(VideoService, "_generate_asr_summary", fail_summary, raising=False)
    service = VideoService(db_path=db_path, asr_adapter=SuccessAdapter())

    result = service.process_video_asr(video["id"])

    assert result["summary_text"] == ""
    assert result["summary_status"] == "failed"
    assert "总结失败" in result["summary_error_message"]
    stored_video = video_repo.get(video["id"])
    assert stored_video["asr_status"] == "success"
    assert stored_video["asr_error_message"] is None
