import json
from pathlib import Path

import httpx


def test_tts_adapter_clone_posts_http_and_returns_audio_path(tmp_path):
    from platform_app.services.tts_adapter import TtsAdapter

    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["path"] = request.url.path
        captured["payload"] = request.read().decode("utf-8")
        target = tmp_path / "clone.wav"
        target.write_bytes(b"wav")
        return httpx.Response(200, json={"tts_audio_path": str(target.resolve())})

    adapter = TtsAdapter(
        service_base_url="http://tts.local",
        transport=httpx.MockTransport(handler),
    )

    result = adapter.clone_from_video(
        video_path=str(tmp_path / "base.mp4"),
        text="新的文案",
        output_path=str(tmp_path / "clone.wav"),
        ref_duration=5.0,
        asr_device="cuda:0",
        tts_device="cuda:1",
    )

    assert captured["path"] == "/clone"
    payload = json.loads(captured["payload"])
    assert payload["video_path"].endswith("base.mp4")
    assert payload["text"] == "新的文案"
    assert payload["output_path"].endswith("clone.wav")
    assert payload["ref_duration"] == 5.0
    assert payload["asr_device"] == "cuda:0"
    assert payload["tts_device"] == "cuda:1"
    assert result == str((tmp_path / "clone.wav").resolve())


def test_tts_adapter_synthesize_default_posts_http_and_returns_audio_path(tmp_path):
    from platform_app.services.tts_adapter import TtsAdapter

    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["path"] = request.url.path
        captured["payload"] = request.read().decode("utf-8")
        target = tmp_path / "default.wav"
        target.write_bytes(b"wav")
        return httpx.Response(200, json={"tts_audio_path": str(target.resolve())})

    adapter = TtsAdapter(
        service_base_url="http://tts.local",
        transport=httpx.MockTransport(handler),
    )

    result = adapter.synthesize_default(
        text="兜底文案",
        output_path=str(tmp_path / "default.wav"),
        reference_audio_path=str(tmp_path / "ref.wav"),
        reference_text="参考文本",
    )

    assert captured["path"] == "/synthesize-default"
    payload = json.loads(captured["payload"])
    assert payload["text"] == "兜底文案"
    assert payload["output_path"].endswith("default.wav")
    assert payload["reference_audio_path"].endswith("ref.wav")
    assert payload["reference_text"] == "参考文本"
    assert result == str((tmp_path / "default.wav").resolve())
