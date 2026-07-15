import httpx
import pytest

from platform_app.services.algorithm_errors import (
    AlgorithmServiceBusyError,
    AlgorithmServiceProtocolError,
)
from platform_app.settings import get_settings
from platform_app.services.asr_adapter import AsrAdapter, AsrAdapterError


def test_settings_default_modes_are_service(monkeypatch, tmp_path):
    monkeypatch.setenv("BS_MEDIA_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("BS_MEDIA_UPLOADS_DIR", str(tmp_path / "uploads"))
    monkeypatch.setenv("BS_MEDIA_WORK_DIR", str(tmp_path / "work"))
    monkeypatch.delenv("BS_MEDIA_DEFAULT_ASR_MODE", raising=False)
    monkeypatch.delenv("BS_MEDIA_ASR_MODE", raising=False)
    monkeypatch.delenv("BS_MEDIA_TTS_MODE", raising=False)
    monkeypatch.delenv("BS_MEDIA_COMFY_MODE", raising=False)

    settings = get_settings()

    assert settings.default_asr_mode == "service"
    assert settings.asr_mode == "service"
    assert settings.tts_mode == "service"


def test_asr_adapter_defaults_to_service_mode():
    adapter = AsrAdapter()

    assert adapter.mode == "service"


@pytest.mark.parametrize("mode", ["auto", "algorithm"])
def test_asr_adapter_rejects_non_service_modes(mode):
    adapter = AsrAdapter(mode=mode)

    with pytest.raises(AsrAdapterError, match="不支持的 ASR 模式"):
        adapter.transcribe(video_path="/tmp/demo.mp4")


def test_asr_adapter_service_mode_returns_structured_payload():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/transcribe"
        return httpx.Response(
            200,
            json={
                "full_text": "服务识别成功",
                "segments": [{"start_sec": 0.0, "end_sec": 1.0, "text": "服务识别成功"}],
            },
        )

    adapter = AsrAdapter(
        mode="service",
        service_base_url="http://asr.local",
        transport=httpx.MockTransport(handler),
    )

    result = adapter.transcribe(video_path="/tmp/demo.mp4", device="cpu", segment_seconds=30)

    assert result["full_text"] == "服务识别成功"
    assert len(result["segments"]) == 1


def test_asr_adapter_service_mode_requires_full_text():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"segments": []})

    adapter = AsrAdapter(
        mode="service",
        service_base_url="http://asr.local",
        transport=httpx.MockTransport(handler),
    )

    with pytest.raises(AsrAdapterError, match="ASR 结果为空"):
        adapter.transcribe(video_path="/tmp/demo.mp4")


def test_asr_adapter_service_mode_maps_busy_error():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503, json={"error": "service busy"})

    adapter = AsrAdapter(
        mode="service",
        service_base_url="http://asr.local",
        transport=httpx.MockTransport(handler),
    )

    with pytest.raises(AsrAdapterError, match="ASR 服务繁忙"):
        adapter.transcribe(video_path="/tmp/demo.mp4")


def test_asr_adapter_service_mode_rejects_invalid_payload():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"full_text": "ok"})

    adapter = AsrAdapter(
        mode="service",
        service_base_url="http://asr.local",
        transport=httpx.MockTransport(handler),
    )

    with pytest.raises(AsrAdapterError, match="ASR 服务返回结构异常"):
        adapter.transcribe(video_path="/tmp/demo.mp4")


def test_asr_adapter_service_mode_uses_env_default_device(monkeypatch):
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["payload"] = request.read().decode("utf-8")
        return httpx.Response(
            200,
            json={
                "full_text": "服务识别成功",
                "segments": [{"start_sec": 0.0, "end_sec": 1.0, "text": "服务识别成功"}],
            },
        )

    monkeypatch.setenv("BS_MEDIA_ASR_DEVICE", "cuda:0")
    adapter = AsrAdapter(
        mode="service",
        service_base_url="http://asr.local",
        transport=httpx.MockTransport(handler),
    )

    adapter.transcribe(video_path="/tmp/demo.mp4")

    assert '"device":"cuda:0"' in captured["payload"]


def test_asr_adapter_service_mode_omits_device_without_explicit_override(monkeypatch):
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["payload"] = request.read().decode("utf-8")
        return httpx.Response(
            200,
            json={
                "full_text": "服务识别成功",
                "segments": [{"start_sec": 0.0, "end_sec": 1.0, "text": "服务识别成功"}],
            },
        )

    monkeypatch.delenv("BS_MEDIA_ASR_DEVICE", raising=False)
    adapter = AsrAdapter(
        mode="service",
        service_base_url="http://asr.local",
        transport=httpx.MockTransport(handler),
    )

    adapter.transcribe(video_path="/tmp/demo.mp4")

    assert '"device"' not in captured["payload"]
