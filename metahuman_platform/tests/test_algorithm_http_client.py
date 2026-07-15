import httpx
import pytest

from platform_app.services.algorithm_errors import (
    AlgorithmServiceBusyError,
    AlgorithmServiceNotReadyError,
    AlgorithmServiceProtocolError,
    AlgorithmServiceRequestError,
    AlgorithmServiceTimeoutError,
)
from platform_app.services.algorithm_http_client import AlgorithmHttpClient
from platform_app.settings import get_settings


def test_settings_expose_algorithm_service_urls(monkeypatch, tmp_path):
    monkeypatch.setenv("BS_MEDIA_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("BS_MEDIA_UPLOADS_DIR", str(tmp_path / "uploads"))
    monkeypatch.setenv("BS_MEDIA_WORK_DIR", str(tmp_path / "work"))
    monkeypatch.setenv("BS_MEDIA_ASR_MODE", "service")
    monkeypatch.setenv("BS_MEDIA_TTS_MODE", "legacy")
    monkeypatch.setenv("BS_MEDIA_COMFY_MODE", "mock")
    monkeypatch.setenv("BS_MEDIA_ASR_SERVICE_HOST", "127.0.0.2")
    monkeypatch.setenv("BS_MEDIA_ASR_SERVICE_PORT", "7100")
    monkeypatch.setenv("BS_MEDIA_TTS_SERVICE_PORT", "7101")
    monkeypatch.setenv("BS_MEDIA_COMFY_SERVICE_PORT", "7102")
    monkeypatch.setenv("BS_MEDIA_ALGO_CONNECT_TIMEOUT_SEC", "5")
    monkeypatch.setenv("BS_MEDIA_ALGO_READ_TIMEOUT_SEC", "120")

    settings = get_settings()

    assert settings.asr_mode == "service"
    assert settings.tts_mode == "legacy"
    assert settings.comfy_mode == "mock"
    assert settings.asr_service_base_url == "http://127.0.0.2:7100"
    assert settings.tts_service_base_url == "http://127.0.0.1:7101"
    assert settings.comfy_service_base_url == "http://127.0.0.1:7102"
    assert settings.algo_connect_timeout_sec == 5
    assert settings.algo_read_timeout_sec == 120


def test_algorithm_http_client_returns_json_payload():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/transcribe"
        return httpx.Response(200, json={"full_text": "ok", "segments": []})

    client = AlgorithmHttpClient(
        base_url="http://algo.local",
        service_name="ASR",
        transport=httpx.MockTransport(handler),
    )

    payload = client.post_json("/transcribe", json={"video_path": "/tmp/demo.mp4"})

    assert payload["full_text"] == "ok"


def test_algorithm_http_client_maps_timeout():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("timeout", request=request)

    client = AlgorithmHttpClient(
        base_url="http://algo.local",
        service_name="ASR",
        transport=httpx.MockTransport(handler),
    )

    with pytest.raises(AlgorithmServiceTimeoutError):
        client.get_json("/ready")


def test_algorithm_http_client_maps_non_json_response():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text="not json")

    client = AlgorithmHttpClient(
        base_url="http://algo.local",
        service_name="TTS",
        transport=httpx.MockTransport(handler),
    )

    with pytest.raises(AlgorithmServiceProtocolError):
        client.get_json("/health")


def test_algorithm_http_client_maps_busy_error():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503, json={"error": "service busy"})

    client = AlgorithmHttpClient(
        base_url="http://algo.local",
        service_name="视频生成",
        transport=httpx.MockTransport(handler),
    )

    with pytest.raises(AlgorithmServiceBusyError):
        client.post_json("/jobs", json={"task_id": "task-1"})


def test_algorithm_http_client_maps_not_ready_error():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503, json={"error": "not ready"})

    client = AlgorithmHttpClient(
        base_url="http://algo.local",
        service_name="TTS",
        transport=httpx.MockTransport(handler),
    )

    with pytest.raises(AlgorithmServiceNotReadyError):
        client.get_json("/ready")


def test_algorithm_http_client_reads_nested_detail_error():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, json={"detail": {"error": "TTS 执行失败: boom"}})

    client = AlgorithmHttpClient(
        base_url="http://algo.local",
        service_name="TTS",
        transport=httpx.MockTransport(handler),
    )

    with pytest.raises(AlgorithmServiceRequestError, match="TTS 执行失败: boom"):
        client.post_json("/clone", json={"video_path": "/tmp/demo.mp4"})


def test_algorithm_http_client_maps_request_error():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("down", request=request)

    client = AlgorithmHttpClient(
        base_url="http://algo.local",
        service_name="ASR",
        transport=httpx.MockTransport(handler),
    )

    with pytest.raises(AlgorithmServiceRequestError):
        client.post_json("/transcribe", json={"video_path": "/tmp/demo.mp4"})


def test_algorithm_http_client_disables_env_proxy(monkeypatch):
    captured = {}
    real_client = httpx.Client

    class RecordingClient(real_client):
        def __init__(self, *args, **kwargs):
            captured["trust_env"] = kwargs.get("trust_env")
            super().__init__(*args, **kwargs)

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"status": "ok"})

    monkeypatch.setattr("platform_app.services.algorithm_http_client.httpx.Client", RecordingClient)
    client = AlgorithmHttpClient(
        base_url="http://algo.local",
        service_name="ASR",
        transport=httpx.MockTransport(handler),
    )

    payload = client.get_json("/health")

    assert payload["status"] == "ok"
    assert captured["trust_env"] is False
