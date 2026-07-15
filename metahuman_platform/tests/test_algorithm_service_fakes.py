from pathlib import Path

from tests.fakes.algorithm_service_fakes import (
    FakeGenerationAdapter,
    FakeLipSyncGenerationAdapter,
    FakePreprocessAdapter,
)


def test_phase2_fake_generation_adapter_creates_expected_files(tmp_path):
    adapter = FakeGenerationAdapter(tmp_path / "temp", tmp_path / "generated")
    result = adapter.generate(
        task_id="task-1",
        item_id="item-1",
        segment_file_path=str(tmp_path / "segment.mp4"),
        segment_asr_text="原始口播",
        prompt_text="卖点提示",
        product_doc_text="",
        aspect_mode="default",
        resolution="720p",
        subtitle_enabled=True,
    )

    assert Path(result["tts_audio_path"]).exists()
    assert Path(result["output_video_url"]).exists()
    assert Path(result["output_video_url"]).parent == (tmp_path / "generated" / "remix" / "task-1").resolve()


def test_phase3_fake_adapter_generates_candidates_and_final_video(tmp_path):
    adapter = FakeLipSyncGenerationAdapter(tmp_path / "temp", tmp_path / "generated")
    candidates = adapter.generate_script_candidates(
        base_video_path=str(tmp_path / "base.mp4"),
        base_video_asr_text="基础文案",
        prompt_text="面膜补水",
        product_doc_text="",
        count=2,
    )
    submitted = adapter.submit_generation(
        task_id="task-1",
        base_video_path=str(tmp_path / "base.mp4"),
        script_text=candidates[0]["content"],
        aspect_mode="default",
        resolution="720p",
        subtitle_enabled=True,
    )
    pending = adapter.poll_generation(task_id="task-1", video_job_id=submitted["video_job_id"])
    success = adapter.poll_generation(task_id="task-1", video_job_id=submitted["video_job_id"])

    assert len(candidates) == 2
    assert pending["status"] == "pending"
    assert success["status"] == "success"
    assert Path(success["output_video_url"]).exists()


def test_phase2_fake_preprocess_adapter_writes_segments(tmp_path):
    adapter = FakePreprocessAdapter(tmp_path / "work")
    result = adapter.build_segments(
        video_id="video-1",
        video_path=str(tmp_path / "base.mp4"),
        asr_full_text="完整文本",
        asr_segments=[{"start_sec": 0.0, "end_sec": 1.0, "text": "第一句"}],
    )

    assert len(result) == 1
    assert Path(result[0]["segment_file_path"]).exists()
