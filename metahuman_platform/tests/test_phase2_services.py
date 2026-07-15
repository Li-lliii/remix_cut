from pathlib import Path

from platform_app.db import init_db
from platform_app.repositories.asr_repository import AsrRepository
from platform_app.repositories.preprocess_job_repository import PreprocessJobRepository
from platform_app.repositories.remix_repository import RemixSegmentRepository, RemixTaskRepository
from platform_app.repositories.review_repository import ReviewRecordRepository
from platform_app.repositories.role_repository import RoleRepository
from platform_app.repositories.video_repository import VideoRepository
from platform_app.services.preprocess_service import PreprocessService
from platform_app.services.remix_service import RemixService
from tests.fakes.algorithm_service_fakes import FakeGenerationAdapter, FakePreprocessAdapter


def _prepare_context(tmp_path):
    db_path = tmp_path / "app.db"
    init_db(db_path)
    role_repo = RoleRepository(db_path)
    video_repo = VideoRepository(db_path)
    asr_repo = AsrRepository(db_path)

    role = role_repo.create(name="角色A", description="", tags=[], avatar_url="")
    video_dir = tmp_path / "uploads" / role["id"]
    video_dir.mkdir(parents=True, exist_ok=True)
    video_path = video_dir / "source.mp4"
    video_path.write_bytes(b"source video")
    video = video_repo.create(
        role_id=role["id"],
        title="source.mp4",
        file_path=str(video_path),
        thumbnail_url="",
        duration_sec=24.0,
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
    return db_path, role, video


def test_preprocess_service_creates_and_reuses_segments(tmp_path):
    db_path, role, video = _prepare_context(tmp_path)
    service = PreprocessService(
        db_path=db_path,
        temp_dir=tmp_path / "temp",
        work_dir=tmp_path / "work",
        preprocess_adapter=FakePreprocessAdapter(tmp_path / "work"),
    )

    first = service.ensure_preprocess(video["id"])
    assert first["reused"] is False
    assert first["job"]["status"] == "success"
    assert len(first["segments"]) == 2
    assert Path(first["segments"][0]["segment_file_path"]).exists()
    assert "temp" not in Path(first["segments"][0]["segment_file_path"]).parts
    assert Path(first["segments"][0]["segment_file_path"]).parent.parts[-4:] == (
        "generated",
        "preprocess",
        video["id"],
        "segments",
    )

    second = service.ensure_preprocess(video["id"])
    assert second["reused"] is True
    assert len(second["segments"]) == 2


def test_preprocess_service_cancel_cleans_segments_but_keeps_asr(tmp_path):
    db_path, _, video = _prepare_context(tmp_path)
    preprocess = PreprocessService(
        db_path=db_path,
        temp_dir=tmp_path / "temp",
        work_dir=tmp_path / "work",
        preprocess_adapter=FakePreprocessAdapter(tmp_path / "work"),
    )
    result = preprocess.ensure_preprocess(video["id"])
    PreprocessJobRepository(db_path).update_status(
        result["job"]["id"],
        status="running",
        progress=60,
    )

    cancelled = preprocess.cancel_job(result["job"]["id"])
    assert cancelled["status"] == "cancelled"
    assert RemixSegmentRepository(db_path).list_by_video(video["id"]) == []
    assert AsrRepository(db_path).get_by_video(video["id"]) is not None


def test_preprocess_service_cancel_does_not_delete_successful_results(tmp_path):
    db_path, _, video = _prepare_context(tmp_path)
    preprocess = PreprocessService(
        db_path=db_path,
        temp_dir=tmp_path / "temp",
        work_dir=tmp_path / "work",
        preprocess_adapter=FakePreprocessAdapter(tmp_path / "work"),
    )
    result = preprocess.ensure_preprocess(video["id"])

    preserved = preprocess.cancel_job(result["job"]["id"])

    assert preserved["status"] == "success"
    assert len(RemixSegmentRepository(db_path).list_by_video(video["id"])) == 2


def test_remix_service_creates_outputs_and_pending_review_records(tmp_path):
    db_path, role, video = _prepare_context(tmp_path)
    preprocess = PreprocessService(
        db_path=db_path,
        temp_dir=tmp_path / "temp",
        work_dir=tmp_path / "work",
        preprocess_adapter=FakePreprocessAdapter(tmp_path / "work"),
    )
    preprocess.ensure_preprocess(video["id"])

    service = RemixService(
        db_path=db_path,
        temp_dir=tmp_path / "temp",
        generated_dir=tmp_path / "generated",
        preprocess_service=preprocess,
        generation_adapter=FakeGenerationAdapter(tmp_path / "temp", tmp_path / "generated"),
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
    service.process_task(task["id"])

    service.get_task_detail(task["id"])
    detail = service.get_task_detail(task["id"])
    assert detail["task"]["status"] == "success"
    assert len(detail["items"]) == 1
    assert detail["items"][0]["rewritten_text"]
    assert Path(detail["items"][0]["tts_audio_path"]).exists()
    assert Path(detail["items"][0]["output_video_url"]).exists()
    reviews = ReviewRecordRepository(db_path).list_pending()
    assert len(reviews) == 1
    assert reviews[0]["source_task_id"] == detail["items"][0]["id"]


def test_remix_service_submits_prompt_and_finishes_after_poll(tmp_path):
    db_path, role, video = _prepare_context(tmp_path)
    preprocess = PreprocessService(
        db_path=db_path,
        temp_dir=tmp_path / "temp",
        work_dir=tmp_path / "work",
        preprocess_adapter=FakePreprocessAdapter(tmp_path / "work"),
    )
    preprocess.ensure_preprocess(video["id"])
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

    first_state = service.process_task(task["id"])
    first_items = RemixTaskRepository(db_path).list_items(task["id"])
    running_detail = service.get_task_detail(task["id"])
    first_detail = service.get_task_detail(task["id"])

    assert first_state["status"] == "running"
    assert first_items[0]["status"] == "video_generating"
    assert first_items[0]["comfy_prompt_id"].startswith("prompt-")
    assert running_detail["task"]["status"] == "running"
    assert first_detail["task"]["status"] == "success"
    assert first_detail["items"][0]["comfy_prompt_id"].startswith("prompt-")
    assert Path(first_detail["items"][0]["tts_audio_path"]).exists()
    assert Path(first_detail["items"][0]["output_video_url"]).exists()


def test_remix_service_run_task_finishes_without_manual_poll(tmp_path):
    db_path, role, video = _prepare_context(tmp_path)
    preprocess = PreprocessService(
        db_path=db_path,
        temp_dir=tmp_path / "temp",
        work_dir=tmp_path / "work",
        preprocess_adapter=FakePreprocessAdapter(tmp_path / "work"),
    )
    preprocess.ensure_preprocess(video["id"])
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

    final_state = service.run_task(task["id"])

    assert final_state["status"] == "success"
    detail = service.get_task_detail(task["id"])
    assert detail["task"]["status"] == "success"
    assert Path(detail["items"][0]["output_video_url"]).exists()
    assert ReviewRecordRepository(db_path).list_pending()[0]["source_task_id"] == detail["items"][0]["id"]


def test_remix_service_cancel_removes_temp_files(tmp_path):
    db_path, role, video = _prepare_context(tmp_path)
    preprocess = PreprocessService(
        db_path=db_path,
        temp_dir=tmp_path / "temp",
        work_dir=tmp_path / "work",
        preprocess_adapter=FakePreprocessAdapter(tmp_path / "work"),
    )
    preprocess.ensure_preprocess(video["id"])
    service = RemixService(
        db_path=db_path,
        temp_dir=tmp_path / "temp",
        generated_dir=tmp_path / "generated",
        preprocess_service=preprocess,
    )
    task = RemixTaskRepository(db_path).create_task(
        role_id=role["id"],
        source_video_id=video["id"],
        prompt_text="卖点提示",
        product_doc_url="",
        target_count=1,
        is_max_mode=False,
        aspect_mode="default",
        resolution="720p",
        subtitle_enabled=True,
        status="running",
    )
    segment = RemixSegmentRepository(db_path).list_by_video(video["id"])[0]
    item = RemixTaskRepository(db_path).create_items(task["id"], [segment["id"]])[0]
    tts_path = tmp_path / "temp" / "tts.wav"
    output_path = tmp_path / "generated" / "result.mp4"
    tts_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    tts_path.write_bytes(b"tts")
    output_path.write_bytes(b"video")
    RemixTaskRepository(db_path).update_item(
        item["id"],
        status="video_generating",
        tts_audio_path=str(tts_path),
        output_video_url=str(output_path),
    )

    cancelled = service.cancel_task(task["id"])
    assert cancelled["status"] == "cancelled"
    assert not tts_path.exists()
    assert not output_path.exists()


def test_remix_service_cancel_does_not_touch_successful_outputs(tmp_path):
    db_path, role, video = _prepare_context(tmp_path)
    preprocess = PreprocessService(
        db_path=db_path,
        temp_dir=tmp_path / "temp",
        work_dir=tmp_path / "work",
        preprocess_adapter=FakePreprocessAdapter(tmp_path / "work"),
    )
    preprocess.ensure_preprocess(video["id"])

    service = RemixService(
        db_path=db_path,
        temp_dir=tmp_path / "temp",
        generated_dir=tmp_path / "generated",
        preprocess_service=preprocess,
        generation_adapter=FakeGenerationAdapter(tmp_path / "temp", tmp_path / "generated"),
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
    service.process_task(task["id"])

    service.get_task_detail(task["id"])
    detail = service.get_task_detail(task["id"])
    preserved = service.cancel_task(task["id"])

    assert preserved["status"] == "success"
    assert Path(detail["items"][0]["tts_audio_path"]).exists()
    assert Path(detail["items"][0]["output_video_url"]).exists()


def test_remix_service_fails_when_preprocess_produces_no_segments(tmp_path):
    db_path, role, video = _prepare_context(tmp_path)

    class EmptyPreprocessAdapter:
        def build_segments(self, *, video_id: str, video_path: str, asr_full_text: str, asr_segments: list[dict]):
            del video_id, video_path, asr_full_text, asr_segments
            return []

    preprocess = PreprocessService(
        db_path=db_path,
        temp_dir=tmp_path / "temp",
        work_dir=tmp_path / "work",
        preprocess_adapter=EmptyPreprocessAdapter(),
    )
    service = RemixService(
        db_path=db_path,
        temp_dir=tmp_path / "temp",
        generated_dir=tmp_path / "generated",
        preprocess_service=preprocess,
        generation_adapter=FakeGenerationAdapter(tmp_path / "temp", tmp_path / "generated"),
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

    final_state = service.process_task(task["id"])

    assert final_state["status"] == "failed"
    assert final_state["error_message"] == "预处理未产出可用混剪片段"
    assert RemixTaskRepository(db_path).list_items(task["id"]) == []


def test_remix_service_treats_long_product_doc_as_text_instead_of_path(tmp_path):
    db_path, role, video = _prepare_context(tmp_path)
    preprocess = PreprocessService(
        db_path=db_path,
        temp_dir=tmp_path / "temp",
        work_dir=tmp_path / "work",
        preprocess_adapter=FakePreprocessAdapter(tmp_path / "work"),
    )
    preprocess.ensure_preprocess(video["id"])
    generation = FakeGenerationAdapter(tmp_path / "temp", tmp_path / "generated")
    service = RemixService(
        db_path=db_path,
        temp_dir=tmp_path / "temp",
        generated_dir=tmp_path / "generated",
        preprocess_service=preprocess,
        generation_adapter=generation,
    )
    long_product_doc = "卖点说明：" + ("这是一个很长的商品文档，用来验证不会被当成文件路径。" * 10)
    task = service.create_task(
        role_id=role["id"],
        source_video_id=video["id"],
        prompt_text="卖点提示",
        product_doc_path=long_product_doc,
        target_count=1,
        is_max_mode=False,
        aspect_mode="default",
        resolution="720p",
        subtitle_enabled=True,
    )

    first_state = service.process_task(task["id"])

    assert first_state["status"] == "running"
    first_detail = service.get_task_detail(task["id"])
    final_detail = service.get_task_detail(task["id"])

    assert first_detail["task"]["status"] == "running"
    assert final_detail["task"]["status"] == "success"
    assert final_detail["items"][0]["rewritten_text"]
    assert final_detail["items"][0]["error_message"] is None
