import json
from pathlib import Path
import subprocess

import httpx

from phase2_algorithms.remix_pipeline import (
    build_remix_segments,
    build_sales_clip_candidates,
    classify_sales_segments_with_llm,
    concat_video_clips,
    cut_video_clip,
    generate_remix_output,
    resolve_bridge_segments,
)


def test_build_remix_segments_creates_real_clips_and_required_fields(tmp_path, monkeypatch):
    video_path = tmp_path / "source.mp4"
    video_path.write_bytes(b"source video")
    output_dir = tmp_path / "work" / "generated" / "preprocess" / "video-1" / "segments"

    monkeypatch.setattr(
        "phase2_algorithms.remix_pipeline.detect_sales_segments_from_asr",
        lambda **kwargs: [
            {
                "start_sec": 1.0,
                "end_sec": 3.5,
                "duration_sec": 2.5,
                "asr_text": "这是一个卖货片段",
            }
        ],
    )

    def fake_cut_video_clip(*, video_path: str, start_sec: float, end_sec: float, output_path: str):
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        Path(output_path).write_bytes(
            f"{video_path}|{start_sec:.3f}|{end_sec:.3f}".encode("utf-8")
        )

    monkeypatch.setattr("phase2_algorithms.remix_pipeline.cut_video_clip", fake_cut_video_clip)

    result = build_remix_segments(
        video_id="video-1",
        video_path=str(video_path),
        asr_full_text="这是完整文本",
        asr_segments=[
            {"start_sec": 0.0, "end_sec": 2.0, "text": "这是一个卖货片段"},
        ],
        output_dir=str(output_dir),
    )

    assert len(result) == 1
    first = result[0]
    assert first["segment_id"]
    assert first["start_sec"] == 1.0
    assert first["end_sec"] == 3.5
    assert first["duration_sec"] == 2.5
    assert first["asr_text"] == "这是一个卖货片段"
    assert Path(first["segment_file_path"]).is_absolute()
    assert Path(first["segment_file_path"]).exists()
    assert Path(first["segment_file_path"]).parent == output_dir.resolve()
    assert Path(first["segment_file_path"]).name == f'{first["segment_id"]}.mp4'


def test_generate_remix_output_returns_required_paths(tmp_path, monkeypatch):
    segment_path = tmp_path / "segments" / "clip-1.mp4"
    segment_path.parent.mkdir(parents=True, exist_ok=True)
    segment_path.write_bytes(b"segment video")
    temp_dir = tmp_path / "temp" / "remix"
    output_dir = tmp_path / "generated" / "remix"

    monkeypatch.setattr(
        "phase2_algorithms.remix_pipeline.rewrite_sales_text",
        lambda **kwargs: "改写后的卖货文案",
    )

    def fake_generate_tts(*, segment_video_path: str, rewritten_text: str, temp_dir: str, task_item_id: str):
        audio_path = Path(temp_dir) / f"{task_item_id}.wav"
        audio_path.parent.mkdir(parents=True, exist_ok=True)
        audio_path.write_bytes(f"{segment_video_path}|{rewritten_text}".encode("utf-8"))
        return str(audio_path.resolve())

    def fake_generate_video(
        *,
        segment_video_path: str,
        tts_audio_path: str,
        output_dir: str,
        task_item_id: str,
        aspect_mode: str,
        resolution: str,
        subtitle_enabled: bool,
    ):
        video_path = Path(output_dir) / f"{task_item_id}.mp4"
        video_path.parent.mkdir(parents=True, exist_ok=True)
        video_path.write_bytes(
            f"{segment_video_path}|{tts_audio_path}|{aspect_mode}|{resolution}|{subtitle_enabled}".encode(
                "utf-8"
            )
        )
        return str(video_path.resolve())

    monkeypatch.setattr("phase2_algorithms.remix_pipeline.generate_tts_audio", fake_generate_tts)
    monkeypatch.setattr("phase2_algorithms.remix_pipeline.generate_remix_video", fake_generate_video)

    result = generate_remix_output(
        task_id="task-1",
        task_item_id="item-1",
        segment_video_path=str(segment_path),
        segment_asr_text="原始卖货文案",
        product_prompt="主打补水保湿",
        product_doc_text="适用熬夜人群",
        aspect_mode="default",
        resolution="720p",
        subtitle_enabled=True,
        temp_dir=str(temp_dir),
        output_dir=str(output_dir),
    )

    assert result["rewritten_text"] == "改写后的卖货文案"
    assert Path(result["tts_audio_path"]).exists()
    assert Path(result["output_video_url"]).exists()
    assert Path(result["tts_audio_path"]).parent == temp_dir.resolve()
    assert Path(result["output_video_url"]).parent == output_dir.resolve()


def test_generate_tts_audio_uses_service_mode(tmp_path, monkeypatch):
    from phase2_algorithms.remix_pipeline import generate_tts_audio

    captured = {}

    class FakeAdapter:
        def clone_from_video(self, **kwargs):
            captured.update(kwargs)
            target = tmp_path / "temp" / "item-1.wav"
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(b"wav")
            return str(target.resolve())

    monkeypatch.setattr("phase2_algorithms.remix_pipeline._get_tts_adapter", lambda: FakeAdapter())
    monkeypatch.setattr(
        "phase2_algorithms.remix_pipeline._load_config",
        lambda config_path=None: {"tts": {"ref_duration": 5.0, "device": "cpu"}},
    )

    result = generate_tts_audio(
        segment_video_path=str(tmp_path / "segment.mp4"),
        rewritten_text="新的卖货文案",
        temp_dir=str(tmp_path / "temp"),
        task_item_id="item-1",
    )

    assert captured["video_path"].endswith("segment.mp4")
    assert captured["text"] == "新的卖货文案"
    assert captured["output_path"].endswith("item-1.wav")
    assert result.endswith("item-1.wav")


def test_generate_tts_audio_service_mode_omits_device_fields_without_explicit_config(tmp_path, monkeypatch):
    from phase2_algorithms.remix_pipeline import generate_tts_audio

    captured = {}

    class FakeAdapter:
        def clone_from_video(self, **kwargs):
            captured.update(kwargs)
            target = tmp_path / "temp" / "item-2.wav"
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(b"wav")
            return str(target.resolve())

    monkeypatch.setattr("phase2_algorithms.remix_pipeline._get_tts_adapter", lambda: FakeAdapter())
    monkeypatch.setattr(
        "phase2_algorithms.remix_pipeline._load_config",
        lambda config_path=None: {"tts": {"ref_duration": 5.0}},
    )

    result = generate_tts_audio(
        segment_video_path=str(tmp_path / "segment.mp4"),
        rewritten_text="新的卖货文案",
        temp_dir=str(tmp_path / "temp"),
        task_item_id="item-2",
    )

    assert "asr_device" not in captured
    assert "tts_device" not in captured
    assert result.endswith("item-2.wav")


def test_generate_tts_audio_service_mode_omits_device_fields_for_gpu_config(tmp_path, monkeypatch):
    from phase2_algorithms.remix_pipeline import generate_tts_audio

    captured = {}

    class FakeAdapter:
        def clone_from_video(self, **kwargs):
            captured.update(kwargs)
            target = tmp_path / "temp" / "item-3.wav"
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(b"wav")
            return str(target.resolve())

    monkeypatch.setattr("phase2_algorithms.remix_pipeline._get_tts_adapter", lambda: FakeAdapter())
    monkeypatch.setattr(
        "phase2_algorithms.remix_pipeline._load_config",
        lambda config_path=None: {"tts": {"ref_duration": 5.0, "device": "cuda:3"}},
    )

    result = generate_tts_audio(
        segment_video_path=str(tmp_path / "segment.mp4"),
        rewritten_text="新的卖货文案",
        temp_dir=str(tmp_path / "temp"),
        task_item_id="item-3",
    )

    assert "asr_device" not in captured
    assert "tts_device" not in captured
    assert result.endswith("item-3.wav")


def test_generate_tts_audio_uses_http_adapter_without_legacy_branch(tmp_path, monkeypatch):
    from phase2_algorithms.remix_pipeline import generate_tts_audio

    captured = {}

    class FakeAdapter:
        def clone_from_video(self, **kwargs):
            captured.update(kwargs)
            target = tmp_path / "temp" / "item-4.wav"
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(b"wav")
            return str(target.resolve())

    monkeypatch.delenv("BS_MEDIA_TTS_MODE", raising=False)
    monkeypatch.setattr("phase2_algorithms.remix_pipeline._get_tts_adapter", lambda: FakeAdapter())
    monkeypatch.setattr("phase2_algorithms.remix_pipeline.subprocess.run", lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("不应调用本地脚本")))
    monkeypatch.setattr(
        "phase2_algorithms.remix_pipeline._load_config",
        lambda config_path=None: {"tts": {"ref_duration": 5.0}},
    )

    result = generate_tts_audio(
        segment_video_path=str(tmp_path / "segment.mp4"),
        rewritten_text="新的卖货文案",
        temp_dir=str(tmp_path / "temp"),
        task_item_id="item-4",
    )

    assert captured["video_path"].endswith("segment.mp4")
    assert captured["text"] == "新的卖货文案"
    assert captured["output_path"].endswith("item-4.wav")
    assert result.endswith("item-4.wav")


def test_classify_sales_segments_with_llm_returns_three_way_labels(monkeypatch):
    outputs = iter(["sales", "chat", "bridge"])

    monkeypatch.setattr(
        "phase2_algorithms.remix_pipeline._get_sales_detect_llm_config",
        lambda config_path=None: {
            "base_url": "http://llm.local",
            "api_key": "test",
            "model": "mock",
            "timeout": 30,
            "temperature": 0.0,
            "top_p": 1.0,
            "max_tokens": 8,
            "enable_thinking": False,
        },
    )
    monkeypatch.setitem(
        __import__("sys").modules,
        "utils.llm_client",
        type(
            "FakeLlmModule",
            (),
            {"call_llm": staticmethod(lambda **kwargs: next(outputs))},
        )(),
    )

    results = classify_sales_segments_with_llm(
        asr_segments=[
            {"id": "seg-1", "start_sec": 0.0, "end_sec": 10.0, "text": "这个产品今天活动价"},
            {"id": "seg-2", "start_sec": 10.0, "end_sec": 16.0, "text": "谢谢大家支持直播间"},
            {"id": "seg-3", "start_sec": 16.0, "end_sec": 22.0, "text": "我跟你说这个真的很重要"},
        ]
    )

    assert [item["classification"] for item in results] == ["sales", "chat", "bridge"]
    assert results[0]["asr_text"] == "这个产品今天活动价"
    assert results[2]["duration_sec"] == 6.0


def test_resolve_bridge_segments_keeps_bridge_when_adjacent_to_sales():
    resolved = resolve_bridge_segments(
        [
            {"id": "seg-1", "start_sec": 0.0, "end_sec": 20.0, "duration_sec": 20.0, "asr_text": "先讲价格", "classification": "sales"},
            {"id": "seg-2", "start_sec": 20.0, "end_sec": 28.0, "duration_sec": 8.0, "asr_text": "我跟你说这个很关键", "classification": "bridge"},
            {"id": "seg-3", "start_sec": 28.0, "end_sec": 36.0, "duration_sec": 8.0, "asr_text": "继续承接一下", "classification": "bridge"},
            {"id": "seg-4", "start_sec": 36.0, "end_sec": 50.0, "duration_sec": 14.0, "asr_text": "再讲优惠机制", "classification": "sales"},
            {"id": "seg-5", "start_sec": 50.0, "end_sec": 58.0, "duration_sec": 8.0, "asr_text": "谢谢大家刷礼物", "classification": "chat"},
            {"id": "seg-6", "start_sec": 58.0, "end_sec": 66.0, "duration_sec": 8.0, "asr_text": "这个真的很好", "classification": "bridge"},
        ]
    )

    assert resolved[0]["keep_flag"] is True
    assert resolved[1]["keep_flag"] is True
    assert resolved[2]["keep_flag"] is True
    assert resolved[3]["keep_flag"] is True
    assert resolved[4]["keep_flag"] is False
    assert resolved[5]["keep_flag"] is False


def test_build_sales_clip_candidates_skips_chat_and_splits_near_pause_after_ninety_seconds():
    candidates = build_sales_clip_candidates(
        [
            {"id": "seg-1", "start_sec": 0.0, "end_sec": 32.0, "duration_sec": 32.0, "asr_text": "第一段卖点", "classification": "sales", "keep_flag": True},
            {"id": "seg-2", "start_sec": 32.0, "end_sec": 40.0, "duration_sec": 8.0, "asr_text": "过渡承接", "classification": "bridge", "keep_flag": True},
            {"id": "seg-3", "start_sec": 40.0, "end_sec": 64.0, "duration_sec": 24.0, "asr_text": "继续讲机制", "classification": "sales", "keep_flag": True},
            {"id": "seg-4", "start_sec": 64.0, "end_sec": 76.0, "duration_sec": 12.0, "asr_text": "谢谢大家", "classification": "chat", "keep_flag": False},
            {"id": "seg-5", "start_sec": 76.0, "end_sec": 106.0, "duration_sec": 30.0, "asr_text": "继续讲第二个卖点", "classification": "sales", "keep_flag": True},
            {"id": "seg-6", "start_sec": 112.0, "end_sec": 130.0, "duration_sec": 18.0, "asr_text": "第三个卖点收尾", "classification": "sales", "keep_flag": True},
        ],
        min_duration_sec=40.0,
        max_duration_sec=90.0,
        pause_gap_sec=5.0,
    )

    assert len(candidates) == 2
    assert candidates[0]["segment_refs"] == ["seg-1", "seg-2", "seg-3"]
    assert candidates[0]["duration_sec"] == 64.0
    assert candidates[0]["source_time_ranges"] == [
        {"start_sec": 0.0, "end_sec": 32.0},
        {"start_sec": 32.0, "end_sec": 40.0},
        {"start_sec": 40.0, "end_sec": 64.0},
    ]
    assert candidates[1]["segment_refs"] == ["seg-5", "seg-6"]
    assert candidates[1]["duration_sec"] == 48.0
    assert "谢谢大家" not in candidates[0]["preview_text"]


def test_build_sales_clip_candidates_splits_continuous_sales_over_ninety_seconds():
    candidates = build_sales_clip_candidates(
        [
            {
                "id": "seg-1",
                "start_sec": 0.0,
                "end_sec": 35.0,
                "duration_sec": 35.0,
                "asr_text": "第一段卖点",
                "classification": "sales",
                "keep_flag": True,
            },
            {
                "id": "seg-2",
                "start_sec": 35.0,
                "end_sec": 70.0,
                "duration_sec": 35.0,
                "asr_text": "第二段卖点",
                "classification": "sales",
                "keep_flag": True,
            },
            {
                "id": "seg-3",
                "start_sec": 70.0,
                "end_sec": 105.0,
                "duration_sec": 35.0,
                "asr_text": "第三段卖点",
                "classification": "sales",
                "keep_flag": True,
            },
        ],
        min_duration_sec=40.0,
        max_duration_sec=90.0,
        pause_gap_sec=5.0,
    )

    assert len(candidates) == 2
    assert candidates[0]["segment_refs"] == ["seg-1"]
    assert candidates[0]["duration_sec"] == 35.0
    assert candidates[1]["segment_refs"] == ["seg-2", "seg-3"]
    assert candidates[1]["duration_sec"] == 70.0
    assert all(item["duration_sec"] <= 90.0 for item in candidates)


def test_cut_and_concat_video_clips_keep_audio_video_durations_close(tmp_path):
    source_path = tmp_path / "source.mp4"
    clip1_path = tmp_path / "clip1.mp4"
    clip2_path = tmp_path / "clip2.mp4"
    joined_path = tmp_path / "joined.mp4"

    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-f",
            "lavfi",
            "-i",
            "testsrc2=size=160x284:rate=24",
            "-f",
            "lavfi",
            "-i",
            "sine=frequency=880:sample_rate=48000",
            "-t",
            "6",
            "-c:v",
            "libx264",
            "-g",
            "48",
            "-keyint_min",
            "48",
            "-sc_threshold",
            "0",
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            "aac",
            "-b:a",
            "128k",
            "-movflags",
            "+faststart",
            str(source_path),
        ],
        check=True,
        capture_output=True,
    )

    clip1 = cut_video_clip(
        video_path=str(source_path),
        start_sec=0.85,
        end_sec=2.75,
        output_path=str(clip1_path),
    )
    clip2 = cut_video_clip(
        video_path=str(source_path),
        start_sec=3.10,
        end_sec=5.20,
        output_path=str(clip2_path),
    )
    joined = concat_video_clips(
        clip_paths=[clip1, clip2],
        output_path=str(joined_path),
    )

    def probe(path: str):
        result = subprocess.run(
            [
                "ffprobe",
                "-v",
                "error",
                "-show_entries",
                "stream=index,codec_type,duration",
                "-of",
                "json",
                path,
            ],
            check=True,
            capture_output=True,
            text=True,
        )
        return json.loads(result.stdout)

    for target in [clip1, clip2, joined]:
        data = probe(str(target))
        durations = {stream["codec_type"]: float(stream["duration"]) for stream in data["streams"]}
        assert "video" in durations
        assert "audio" in durations
        assert abs(durations["video"] - durations["audio"]) < 0.05


def test_poll_remix_video_job_uses_service_mode_without_output_dir(tmp_path, monkeypatch):
    from phase2_algorithms.remix_pipeline import poll_remix_video_job

    captured = {}
    output_path = tmp_path / "result.mp4"
    output_path.write_bytes(b"video")

    def handler(request: httpx.Request) -> httpx.Response:
        captured["path"] = request.url.path
        captured["query"] = str(request.url.query)
        return httpx.Response(
            200,
            json={"status": "success", "output_video_url": str(output_path.resolve())},
        )

    monkeypatch.setenv("BS_MEDIA_COMFY_MODE", "service")
    monkeypatch.setattr(
        "phase2_algorithms.remix_pipeline._get_comfy_client",
        lambda: __import__("platform_app.services.algorithm_http_client", fromlist=["AlgorithmHttpClient"]).AlgorithmHttpClient(
            base_url="http://comfy.local",
            service_name="视频生成",
            transport=httpx.MockTransport(handler),
        ),
    )

    result = poll_remix_video_job(prompt_id="job-1", output_dir=str(tmp_path / "ignored"))

    assert result["status"] == "success"
    assert result["output_video_url"] == str(output_path.resolve())
    assert captured["path"] == "/jobs/job-1"
    assert captured["query"] in {"", "b''"}
