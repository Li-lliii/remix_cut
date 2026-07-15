import builtins
from pathlib import Path

import httpx
import pytest

from phase3_algorithms import lip_sync_pipeline
from phase3_algorithms.duration_estimator import estimate_duration_from_context
from phase3_algorithms.media_generation import _generate_tts_from_default_voice
from phase3_algorithms.script_generation import (
    _clean_candidate_text,
    _call_generation_llm,
    _compute_longest_common_ratio,
    _compute_overlap_ratio,
    _is_weak_asr,
)


def test_phase3_pipeline_exports_required_functions():
    assert callable(lip_sync_pipeline.generate_script_candidates)
    assert callable(lip_sync_pipeline.regenerate_script_candidate)
    assert callable(lip_sync_pipeline.validate_script_tts_duration)
    assert callable(lip_sync_pipeline.validate_script_tts_duration_with_context)
    assert callable(lip_sync_pipeline.submit_lip_sync_generation)
    assert callable(lip_sync_pipeline.poll_lip_sync_generation)


def test_default_voice_asset_exists():
    asset = (
        Path(__file__).resolve().parent.parent
        / "assets"
        / "default_voice"
        / "dongbei_clone_5s.wav"
    )
    assert asset.exists()
    assert asset.is_file()


def test_generate_script_candidates_returns_exact_count_and_estimated_duration(tmp_path, monkeypatch):
    video_path = tmp_path / "base.mp4"
    video_path.write_bytes(b"video")

    monkeypatch.setattr(
        "phase3_algorithms.script_generation._get_video_duration_sec",
        lambda path: 12.0,
    )
    monkeypatch.setattr(
        "phase3_algorithms.script_generation._call_generation_llm",
        lambda **kwargs: [
            "方案一，主打补水修护，适合熬夜后急救。",
            "第二版强调贴合感和舒缓体验，适合夜间护肤。",
            "第三版走强转化口播，突出补水和上脸舒服。",
        ],
    )
    monkeypatch.setattr(
        "phase3_algorithms.lip_sync_pipeline.validate_script_tts_duration_with_context",
        lambda **kwargs: {"estimated_tts_duration_sec": 8.4, "valid": True},
    )

    result = lip_sync_pipeline.generate_script_candidates(
        base_video_path=str(video_path),
        base_video_asr_text="嗯嗯",
        prompt_text="面膜补水，适合熬夜人群",
        product_doc_text="补水、舒缓、贴合",
        count=3,
    )

    assert len(result) == 3
    assert all(item["char_count"] > 0 for item in result)
    assert all(item["estimated_tts_duration_sec"] == 8.4 for item in result)


def test_generate_script_candidates_clamps_count_to_minimum_one(tmp_path, monkeypatch):
    video_path = tmp_path / "base.mp4"
    video_path.write_bytes(b"video")

    monkeypatch.setattr(
        "phase3_algorithms.script_generation._get_video_duration_sec",
        lambda path: 10.0,
    )
    monkeypatch.setattr(
        "phase3_algorithms.script_generation._call_generation_llm",
        lambda **kwargs: ["候选一"],
    )
    monkeypatch.setattr(
        "phase3_algorithms.lip_sync_pipeline.validate_script_tts_duration_with_context",
        lambda **kwargs: {"estimated_tts_duration_sec": 3.0, "valid": True},
    )

    result = lip_sync_pipeline.generate_script_candidates(
        base_video_path=str(video_path),
        base_video_asr_text="原视频口播",
        prompt_text="面膜补水",
        product_doc_text="补水舒缓",
        count=0,
    )

    assert len(result) == 1


def test_generate_script_candidates_raises_when_three_rounds_still_duplicate(tmp_path, monkeypatch):
    video_path = tmp_path / "base.mp4"
    video_path.write_bytes(b"video")

    monkeypatch.setattr(
        "phase3_algorithms.script_generation._get_video_duration_sec",
        lambda path: 12.0,
    )
    monkeypatch.setattr(
        "phase3_algorithms.script_generation._call_generation_llm",
        lambda **kwargs: ["完全相同", "完全相同", "完全相同"],
    )

    with pytest.raises(RuntimeError, match="候选文案生成失败"):
        lip_sync_pipeline.generate_script_candidates(
            base_video_path=str(video_path),
            base_video_asr_text="原视频口播",
            prompt_text="面膜补水",
            product_doc_text="补水",
            count=3,
        )


def test_regenerate_script_candidate_retries_when_too_similar(tmp_path, monkeypatch):
    video_path = tmp_path / "base.mp4"
    video_path.write_bytes(b"video")
    outputs = iter(["原文几乎不变", "原文几乎不变", "表达结构已明显变化的新版本"])

    monkeypatch.setattr(
        "phase3_algorithms.script_generation._get_video_duration_sec",
        lambda path: 10.0,
    )
    monkeypatch.setattr(
        "phase3_algorithms.script_generation._call_single_regeneration_llm",
        lambda **kwargs: next(outputs),
    )
    monkeypatch.setattr(
        "phase3_algorithms.lip_sync_pipeline.validate_script_tts_duration_with_context",
        lambda **kwargs: {"estimated_tts_duration_sec": 6.2, "valid": True},
    )

    result = lip_sync_pipeline.regenerate_script_candidate(
        base_video_path=str(video_path),
        base_video_asr_text="大家好今天推荐一个很好用的补水面膜",
        prompt_text="面膜补水",
        product_doc_text="舒缓补水",
        source_script_text="原文几乎不变",
    )

    assert result["content"] == "表达结构已明显变化的新版本"


def test_script_generation_helpers_match_spec_boundaries():
    assert _compute_overlap_ratio("abcdefg", "abcxxxx") < 0.70
    assert _compute_overlap_ratio("abcdefg", "abcdezz") >= 0.70
    assert _compute_longest_common_ratio("abcdef", "abcxyz") < 0.60
    assert _compute_longest_common_ratio("abcdef", "abcdxy") >= 0.60
    assert _is_weak_asr("补水补水补水补水补水补水补水", 100) is True
    assert _clean_candidate_text('1. “以下是为你生成的文案：补水真的很舒服！”') == "补水真的很舒服"


def test_validate_script_tts_duration_uses_default_speed_without_asr(tmp_path, monkeypatch):
    video_path = tmp_path / "base.mp4"
    video_path.write_bytes(b"video")

    monkeypatch.setattr(
        "phase3_algorithms.duration_estimator._get_video_duration_sec",
        lambda path: 12.0,
    )

    result = lip_sync_pipeline.validate_script_tts_duration(
        base_video_path=str(video_path),
        script_text="这是一段十个字上下的新文案",
    )

    assert result["estimated_tts_duration_sec"] > 0
    assert result["valid"] is True


def test_validate_script_tts_duration_with_context_uses_asr_speed():
    result = lip_sync_pipeline.validate_script_tts_duration_with_context(
        base_video_duration_sec=10.0,
        base_video_asr_text="这是十个字这是十个字这是十个字这是十个字",
        script_text="这是十个字这是十个字",
    )

    assert result["estimated_tts_duration_sec"] == 5.0
    assert result["valid"] is True


def test_estimate_duration_from_context_handles_empty_text_and_invalid_duration():
    assert estimate_duration_from_context("", 0.0, "原视频文本") == 0.0
    assert estimate_duration_from_context("新的文案", 0.0, "原视频文本") > 0.0


def test_submit_lip_sync_generation_writes_real_tts_path_and_job_id(tmp_path, monkeypatch):
    video_path = tmp_path / "base.mp4"
    video_path.write_bytes(b"video")
    temp_dir = tmp_path / "work" / "temp" / "lip_sync" / "task-1"
    output_dir = tmp_path / "work" / "generated" / "lip_sync" / "task-1" / "final"

    monkeypatch.setattr(
        "phase3_algorithms.media_generation._generate_tts_from_video",
        lambda **kwargs: (_ for _ in ()).throw(RuntimeError("静音")),
    )

    def fake_default_tts(**kwargs):
        path = temp_dir / "tts" / "task-1.wav"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"wav")
        return str(path.resolve())

    monkeypatch.setattr(
        "phase3_algorithms.media_generation._generate_tts_from_default_voice",
        fake_default_tts,
    )
    monkeypatch.setattr(
        "phase3_algorithms.media_generation.submit_comfyui_job",
        lambda **kwargs: "job-001",
    )

    result = lip_sync_pipeline.submit_lip_sync_generation(
        task_id="task-1",
        base_video_path=str(video_path),
        script_text="新的最终文案",
        aspect_mode="default",
        resolution="720p",
        subtitle_enabled=True,
        temp_dir=str(temp_dir),
        output_dir=str(output_dir),
    )

    assert result["video_job_id"] == "job-001"
    assert result["tts_audio_path"].endswith("task-1.wav")
    assert Path(result["tts_audio_path"]).is_absolute()
    assert Path(result["tts_audio_path"]).exists()


def test_submit_lip_sync_generation_raises_when_default_voice_missing(tmp_path, monkeypatch):
    video_path = tmp_path / "base.mp4"
    video_path.write_bytes(b"video")

    monkeypatch.setattr(
        "phase3_algorithms.media_generation._generate_tts_from_video",
        lambda **kwargs: (_ for _ in ()).throw(RuntimeError("静音")),
    )
    monkeypatch.setattr(
        "phase3_algorithms.media_generation._get_default_voice_path",
        lambda: tmp_path / "missing.wav",
    )

    with pytest.raises(RuntimeError, match="默认参考音色不存在"):
        lip_sync_pipeline.submit_lip_sync_generation(
            task_id="task-1",
            base_video_path=str(video_path),
            script_text="文案",
            aspect_mode="default",
            resolution="720p",
            subtitle_enabled=True,
            temp_dir=str(tmp_path / "temp"),
            output_dir=str(tmp_path / "final"),
        )


def test_generate_tts_with_fallback_uses_http_adapter_without_local_tts(tmp_path, monkeypatch):
    from phase3_algorithms.media_generation import generate_tts_with_fallback

    calls = []

    class FakeAdapter:
        def clone_from_video(self, **kwargs):
            calls.append(("clone", kwargs))
            raise RuntimeError("clone failed")

        def synthesize_default(self, **kwargs):
            calls.append(("default", kwargs))
            target = tmp_path / "work" / "tts" / "task-9.wav"
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(b"wav")
            return str(target.resolve())

    monkeypatch.delenv("BS_MEDIA_TTS_MODE", raising=False)
    monkeypatch.setattr("phase3_algorithms.media_generation._get_tts_adapter", lambda: FakeAdapter())
    monkeypatch.setattr(
        "phase3_algorithms.media_generation.subprocess.run",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("不应调用本地脚本")),
    )

    result = generate_tts_with_fallback(
        base_video_path=str(tmp_path / "base.mp4"),
        script_text="新的口播文案",
        task_id="task-9",
        temp_dir=str(tmp_path / "work"),
    )

    assert [item[0] for item in calls] == ["clone", "default"]
    assert result.endswith("task-9.wav")


def test_poll_lip_sync_generation_returns_pending_success_and_failed(tmp_path, monkeypatch):
    output_path = tmp_path / "final.mp4"
    output_path.write_bytes(b"video")

    monkeypatch.setattr(
        "phase3_algorithms.media_generation.poll_comfyui_job",
        lambda **kwargs: {"status": "pending"},
    )
    assert lip_sync_pipeline.poll_lip_sync_generation(task_id="task-1", video_job_id="job-1") == {
        "status": "pending"
    }

    monkeypatch.setattr(
        "phase3_algorithms.media_generation.poll_comfyui_job",
        lambda **kwargs: {"status": "success", "output_video_url": str(output_path.resolve())},
    )
    success = lip_sync_pipeline.poll_lip_sync_generation(task_id="task-1", video_job_id="job-1")
    assert success["status"] == "success"
    assert success["output_video_url"] == str(output_path.resolve())

    monkeypatch.setattr(
        "phase3_algorithms.media_generation.poll_comfyui_job",
        lambda **kwargs: {"status": "success", "output_video_url": str(tmp_path / 'missing.mp4')},
    )
    failed = lip_sync_pipeline.poll_lip_sync_generation(task_id="task-1", video_job_id="job-1")
    assert failed == {"status": "failed", "message": "视频生成状态异常"}


def test_poll_lip_sync_generation_returns_failed_when_job_id_missing():
    result = lip_sync_pipeline.poll_lip_sync_generation(task_id="task-1", video_job_id="")
    assert result == {"status": "failed", "message": "缺少有效的视频生成任务ID"}


def test_poll_comfyui_job_uses_given_output_dir(tmp_path, monkeypatch):
    captured = {}

    def fake_run(command, capture_output, text, check):
        del capture_output, text, check
        captured["command"] = command

        class Result:
            stdout = '{"status":"pending","prompt_id":"job-1"}\n'

        return Result()

    monkeypatch.setattr("phase3_algorithms.media_generation.subprocess.run", fake_run)

    output_dir = tmp_path / "generated" / "lip_sync" / "task-1" / "final"
    result = __import__("phase3_algorithms.media_generation", fromlist=["poll_comfyui_job"]).poll_comfyui_job(
        task_id="task-1",
        video_job_id="job-1",
        output_dir=str(output_dir),
    )

    assert result == {"status": "pending"}
    assert "--output-dir" in captured["command"]
    assert captured["command"][-1] == str(output_dir.resolve())


def test_poll_comfyui_job_defaults_to_task_generated_dir_when_output_dir_absent(tmp_path, monkeypatch):
    captured = {}

    def fake_run(command, capture_output, text, check):
        del capture_output, text, check
        captured["command"] = command

        class Result:
            stdout = '{"status":"pending","prompt_id":"job-1"}\n'

        return Result()

    monkeypatch.setattr("phase3_algorithms.media_generation.subprocess.run", fake_run)
    monkeypatch.chdir(tmp_path)

    result = __import__("phase3_algorithms.media_generation", fromlist=["poll_comfyui_job"]).poll_comfyui_job(
        task_id="task-9",
        video_job_id="job-1",
    )

    assert result == {"status": "pending"}
    assert captured["command"][-1] == str(
        (tmp_path / "generated" / "lip_sync" / "task-9" / "final").resolve()
    )


def test_generate_tts_from_video_uses_service_mode(tmp_path, monkeypatch):
    captured = {}

    class FakeAdapter:
        def clone_from_video(self, **kwargs):
            captured.update(kwargs)
            target = tmp_path / "temp" / "tts" / "task-1.wav"
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(b"wav")
            return str(target.resolve())

    monkeypatch.setattr("phase3_algorithms.media_generation._get_tts_adapter", lambda: FakeAdapter())

    result = __import__("phase3_algorithms.media_generation", fromlist=["_generate_tts_from_video"])._generate_tts_from_video(
        base_video_path=str(tmp_path / "base.mp4"),
        script_text="新的文案",
        task_id="task-1",
        temp_dir=str(tmp_path / "temp"),
    )

    assert captured["video_path"].endswith("base.mp4")
    assert captured["text"] == "新的文案"
    assert result.endswith("task-1.wav")


def test_poll_comfyui_job_uses_service_mode_without_output_dir(tmp_path, monkeypatch):
    captured = {}
    output_path = tmp_path / "final.mp4"
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
        "phase3_algorithms.media_generation._get_comfy_client",
        lambda: __import__("platform_app.services.algorithm_http_client", fromlist=["AlgorithmHttpClient"]).AlgorithmHttpClient(
            base_url="http://comfy.local",
            service_name="视频生成",
            transport=httpx.MockTransport(handler),
        ),
    )

    result = __import__("phase3_algorithms.media_generation", fromlist=["poll_comfyui_job"]).poll_comfyui_job(
        task_id="task-1",
        video_job_id="job-1",
        output_dir=str(tmp_path / "ignored"),
    )

    assert result["status"] == "success"
    assert result["output_video_url"] == str(output_path.resolve())
    assert captured["path"] == "/jobs/job-1"
    assert captured["query"] in {"", "b''"}


def test_call_generation_llm_parses_json_array(monkeypatch):
    monkeypatch.setattr(
        "phase3_algorithms.script_generation._get_gen_word_llm_config",
        lambda: {
            "base_url": "http://example.com/v1",
            "api_key": "token",
            "model": "mock-model",
            "timeout": 30,
            "temperature": 0.7,
            "top_p": 0.9,
            "max_tokens": None,
            "enable_thinking": False,
        },
    )
    monkeypatch.setattr(
        "phase3_algorithms.script_generation.call_llm",
        lambda **kwargs: '["第一条文案","第二条文案","第三条文案"]',
    )
    result = _call_generation_llm(
        prompt_text="面膜补水",
        product_doc_text="补水舒缓",
        base_video_asr_text="大家好今天推荐一款面膜",
        target_char_count=60,
        count=3,
    )
    assert result == ["第一条文案", "第二条文案", "第三条文案"]


def test_script_generation_load_config_falls_back_to_tts_conda_env(monkeypatch, tmp_path):
    from phase3_algorithms import script_generation

    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        "llm:\n  gen_word:\n    base_url: \"http://example.com\"\n",
        encoding="utf-8",
    )

    original_import = builtins.__import__
    captured = {}

    def fake_import(name, globals=None, locals=None, fromlist=(), level=0):
        if name == "yaml":
            raise ModuleNotFoundError("No module named 'yaml'")
        return original_import(name, globals, locals, fromlist, level)

    class FakeCompletedProcess:
        def __init__(self, stdout: str):
            self.stdout = stdout

    def fake_run(command, capture_output, text, check):
        captured["command"] = command
        assert capture_output is True
        assert text is True
        assert check is True
        return FakeCompletedProcess('{"llm": {"gen_word": {"base_url": "http://example.com"}}}\n')

    monkeypatch.setattr(script_generation, "REMIX_ROOT", tmp_path)
    monkeypatch.setattr(builtins, "__import__", fake_import)
    monkeypatch.setattr(script_generation.subprocess, "run", fake_run)

    result = script_generation._load_config()

    assert result["llm"]["gen_word"]["base_url"] == "http://example.com"
    assert captured["command"][:5] == ["conda", "run", "-n", "tts", "python"]


def test_generate_tts_from_default_voice_uses_real_synthesis_chain(tmp_path, monkeypatch):
    output_path = tmp_path / "temp" / "tts" / "task-1.wav"
    called = {}

    monkeypatch.setattr(
        "phase3_algorithms.media_generation._get_default_voice_reference_text",
        lambda reference_audio: "这是默认音色参考文本",
    )

    class FakeAdapter:
        def synthesize_default(self, **kwargs):
            called.update(kwargs)
            target = Path(kwargs["output_path"])
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(b"wav")
            return str(target.resolve())

    monkeypatch.setattr("phase3_algorithms.media_generation._get_tts_adapter", lambda: FakeAdapter())

    result = _generate_tts_from_default_voice(
        script_text="新的最终文案",
        task_id="task-1",
        temp_dir=str(tmp_path / "temp"),
    )

    assert Path(result).exists()
    assert called["text"] == "新的最终文案"
    assert called["reference_text"] == "这是默认音色参考文本"


def test_generate_tts_from_video_service_mode_omits_device_fields_without_explicit_config(tmp_path, monkeypatch):
    from phase3_algorithms.media_generation import _generate_tts_from_video

    captured = {}

    class FakeAdapter:
        def clone_from_video(self, **kwargs):
            captured.update(kwargs)
            target = tmp_path / "task-1.wav"
            target.write_bytes(b"wav")
            return str(target.resolve())

    monkeypatch.setattr("phase3_algorithms.media_generation._get_tts_adapter", lambda: FakeAdapter())

    result = _generate_tts_from_video(
        base_video_path=str(tmp_path / "base.mp4"),
        script_text="测试文案",
        task_id="task-1",
        temp_dir=str(tmp_path),
    )

    assert "asr_device" not in captured
    assert "tts_device" not in captured
    assert result.endswith("task-1.wav")
