import logging
from fastapi.testclient import TestClient

from algorithm_services import asr_service


def test_asr_service_warms_backend_on_startup(monkeypatch):
    calls = []

    def fake_warmup_backend():
        calls.append("warmup")
        asr_service._SERVICE_STATE["model_loaded"] = True

    monkeypatch.setattr(asr_service, "_warmup_backend", fake_warmup_backend)
    monkeypatch.setenv("BS_MEDIA_ASR_DEVICE", "cuda:0")
    monkeypatch.setenv("CUDA_VISIBLE_DEVICES", "3")

    with TestClient(asr_service.app) as client:
        assert calls == ["warmup"]
        assert client.get("/health").json() == {
            "status": "ok",
            "default_device": "cuda:0",
            "visible_devices": "3",
        }
        assert client.get("/ready").json() == {
            "status": "ready",
            "model_loaded": True,
            "default_device": "cuda:0",
            "visible_devices": "3",
        }


def test_asr_service_transcribe_audio_returns_text(monkeypatch):
    monkeypatch.setattr(
        asr_service,
        "_run_transcribe_audio",
        lambda *, audio_path, device: {
            "text": f"audio:{audio_path}:{device}",
        },
    )
    monkeypatch.setattr(
        asr_service,
        "_warmup_backend",
        lambda: asr_service._SERVICE_STATE.__setitem__("model_loaded", True),
    )
    monkeypatch.setenv("BS_MEDIA_ASR_DEVICE", "cuda:0")

    with TestClient(asr_service.app) as client:
        response = client.post(
            "/transcribe-audio",
            json={"audio_path": "/abs/path/demo.wav", "device": "cpu"},
        )

    assert response.status_code == 200
    assert response.json()["text"] == "audio:/abs/path/demo.wav:cpu"


def test_asr_service_transcribe_success(monkeypatch, caplog):
    monkeypatch.setattr(
        asr_service,
        "_run_asr",
        lambda *, video_path, device, segment_seconds: {
            "full_text": f"ok:{video_path}:{device}:{segment_seconds}",
            "segments": [{"start_sec": 0.0, "end_sec": 1.0, "text": "ok"}],
        },
    )

    caplog.set_level(logging.INFO)
    with TestClient(asr_service.app) as client:
        response = client.post(
            "/transcribe",
            json={"video_path": "/abs/path/demo.mp4", "device": "cpu", "segment_seconds": 30},
        )

    assert response.status_code == 200
    assert response.json()["full_text"].startswith("ok:/abs/path/demo.mp4")
    assert any("stage=asr_transcribe_start" in record.getMessage() for record in caplog.records)
    assert any("stage=asr_transcribe_success" in record.getMessage() for record in caplog.records)


def test_asr_service_transcribe_failure(monkeypatch, caplog):
    def raise_error(*, video_path, device, segment_seconds):
        del video_path, device, segment_seconds
        raise RuntimeError("ASR 执行失败: boom")

    monkeypatch.setattr(asr_service, "_run_asr", raise_error)

    caplog.set_level(logging.INFO)
    with TestClient(asr_service.app) as client:
        response = client.post(
            "/transcribe",
            json={"video_path": "/abs/path/demo.mp4", "device": "cpu", "segment_seconds": 30},
        )

    assert response.status_code == 500
    assert response.json()["detail"]["error"] == "ASR 执行失败: boom"
    assert any("stage=asr_transcribe_start" in record.getMessage() for record in caplog.records)
    assert any("stage=asr_transcribe_failed" in record.getMessage() for record in caplog.records)
