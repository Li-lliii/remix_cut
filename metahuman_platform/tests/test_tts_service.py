import logging

from fastapi.testclient import TestClient
import pytest

from algorithm_services import tts_service
from utils import tts_gen_sound


@pytest.fixture(autouse=True)
def stub_tts_backend_warmup(monkeypatch):
    monkeypatch.setattr(tts_service.tts_backend, "warmup_tts_model", lambda device=None: object())
    monkeypatch.setattr(tts_service.tts_backend, "is_tts_model_loaded", lambda: True)
    monkeypatch.setattr(tts_service, "_asr_service_ready", lambda: True)
    monkeypatch.setattr(tts_service, "_default_voice_ready", lambda: True)


def test_tts_service_startup_preloads_tts_model_and_ready_reflects_state(monkeypatch):
    warmed = {}

    def fake_warmup_tts_model(*, device=None):
        warmed["device"] = device
        return object()

    monkeypatch.setattr(tts_service.tts_backend, "warmup_tts_model", fake_warmup_tts_model)
    monkeypatch.setenv("BS_MEDIA_TTS_ASR_DEVICE", "cuda:0")
    monkeypatch.setenv("BS_MEDIA_TTS_DEVICE", "cuda:2")
    monkeypatch.setenv("CUDA_VISIBLE_DEVICES", "3")

    with TestClient(tts_service.app) as client:
        assert client.get("/health").json() == {
            "status": "ok",
            "default_asr_device": "cuda:0",
            "default_tts_device": "cuda:2",
            "visible_devices": "3",
        }
        assert client.get("/ready").json() == {
            "status": "ready",
            "model_loaded": True,
            "default_voice_available": True,
            "default_asr_device": "cuda:0",
            "default_tts_device": "cuda:2",
            "visible_devices": "3",
        }

    assert warmed["device"] == "cuda:2"


def test_tts_service_clone_success(monkeypatch, tmp_path, caplog):
    output_path = tmp_path / "clone.wav"
    output_path.write_bytes(b"audio")
    monkeypatch.setenv("BS_MEDIA_TTS_ASR_DEVICE", "cpu")
    monkeypatch.setenv("BS_MEDIA_TTS_DEVICE", "cpu")

    monkeypatch.setattr(
        tts_service,
        "_run_clone",
        lambda **kwargs: {
            "tts_audio_path": str(output_path.resolve()),
            "voice_source": "clone",
            "fallback_used": False,
            "message": "ok",
        },
    )

    caplog.set_level(logging.INFO)
    with TestClient(tts_service.app) as client:
        response = client.post(
            "/clone",
            json={
                "video_path": "/abs/path/base.mp4",
                "text": "你好",
                "output_path": str(output_path),
                "ref_duration": 5.0,
                "asr_device": "cpu",
                "tts_device": "cpu",
            },
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload == {
        "tts_audio_path": str(output_path.resolve()),
        "voice_source": "clone",
        "fallback_used": False,
        "message": "ok",
    }
    assert any("stage=tts_clone_start" in record.getMessage() for record in caplog.records)
    assert any("stage=tts_clone_success" in record.getMessage() for record in caplog.records)


def test_tts_service_clone_requires_asr_service_ready(monkeypatch, tmp_path):
    output_path = tmp_path / "clone.wav"
    output_path.write_bytes(b"audio")
    monkeypatch.setattr(tts_service, "_asr_service_ready", lambda: False)

    with pytest.raises(RuntimeError, match="ASR 服务未就绪"):
        with TestClient(tts_service.app):
            pass


def test_tts_service_ready_reflects_default_voice_unavailable(monkeypatch):
    monkeypatch.setattr(tts_service, "_default_voice_ready", lambda: False)
    monkeypatch.setattr(tts_service, "_ensure_service_ready", lambda: None)

    with TestClient(tts_service.app) as client:
        assert client.get("/ready").json() == {
            "status": "ready",
            "model_loaded": False,
            "default_voice_available": False,
            "default_asr_device": "cuda:0",
            "default_tts_device": "cuda:0",
            "visible_devices": "",
        }


def test_tts_service_startup_requires_default_voice(monkeypatch):
    monkeypatch.setattr(tts_service, "_default_voice_ready", lambda: False)

    with pytest.raises(RuntimeError, match="默认参考音色不存在"):
        with TestClient(tts_service.app):
            pass


def test_tts_service_uses_configured_asr_host_and_port(monkeypatch):
    monkeypatch.delenv("BS_MEDIA_ASR_SERVICE_BASE_URL", raising=False)
    monkeypatch.setenv("BS_MEDIA_ALGO_HOST", "10.0.0.1")
    monkeypatch.setenv("BS_MEDIA_ASR_SERVICE_HOST", "10.0.0.2")
    monkeypatch.setenv("BS_MEDIA_ASR_SERVICE_PORT", "7100")

    assert tts_service._asr_service_base_url() == "http://10.0.0.2:7100"


def test_tts_service_clone_passes_http_asr_resolver(monkeypatch, tmp_path):
    output_path = tmp_path / "clone.wav"
    output_path.write_bytes(b"audio")
    clip_path = tmp_path / "reference_clip.wav"
    clip_path.write_bytes(b"clip")
    calls = {}
    monkeypatch.setenv("BS_MEDIA_TTS_ASR_DEVICE", "cpu")
    monkeypatch.setenv("BS_MEDIA_TTS_DEVICE", "cpu")

    def fake_transcribe_reference_audio_via_asr_service(*, audio_path, device):
        calls["audio_path"] = str(audio_path)
        calls["device"] = device
        return "参考音频文本"

    def fake_tts_from_video(
        *,
        video_path,
        new_text,
        output_path,
        ref_duration,
        asr_device,
        tts_device,
        asr_text_resolver,
    ):
        del video_path, new_text, ref_duration, asr_device, tts_device
        assert callable(asr_text_resolver)
        assert asr_text_resolver(clip_path) == "参考音频文本"
        return output_path

    monkeypatch.setattr(
        tts_service,
        "_transcribe_reference_audio_via_asr_service",
        fake_transcribe_reference_audio_via_asr_service,
    )
    monkeypatch.setattr(tts_service.tts_backend, "tts_from_video", fake_tts_from_video)

    with TestClient(tts_service.app) as client:
        response = client.post(
            "/clone",
            json={
                "video_path": "/abs/path/base.mp4",
                "text": "你好",
                "output_path": str(output_path),
                "ref_duration": 5.0,
                "asr_device": "cpu",
                "tts_device": "cpu",
            },
        )

    assert response.status_code == 200
    assert response.json()["tts_audio_path"] == str(output_path.resolve())
    assert calls == {
        "audio_path": str(clip_path.resolve()),
        "device": "cpu",
    }


def test_tts_service_default_success(monkeypatch, tmp_path, caplog):
    output_path = tmp_path / "default.wav"
    output_path.write_bytes(b"audio")

    monkeypatch.setattr(
        tts_service,
        "_run_default",
        lambda **kwargs: {
            "tts_audio_path": str(output_path.resolve()),
            "voice_source": "default",
            "fallback_used": True,
            "message": "used default reference voice",
        },
    )

    caplog.set_level(logging.INFO)
    with TestClient(tts_service.app) as client:
        response = client.post(
            "/synthesize-default",
            json={
                "text": "你好",
                "output_path": str(output_path),
                "reference_audio_path": str(output_path),
                "reference_text": "参考文案",
            },
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["voice_source"] == "default"
    assert payload["fallback_used"] is True
    assert any("stage=tts_default_start" in record.getMessage() for record in caplog.records)
    assert any("stage=tts_default_success" in record.getMessage() for record in caplog.records)


def test_tts_service_clone_failure(monkeypatch, caplog):
    def raise_error(**kwargs):
        del kwargs
        raise RuntimeError("TTS 执行失败: boom")

    monkeypatch.setattr(tts_service, "_run_clone", raise_error)
    monkeypatch.setenv("BS_MEDIA_TTS_ASR_DEVICE", "cpu")
    monkeypatch.setenv("BS_MEDIA_TTS_DEVICE", "cpu")

    caplog.set_level(logging.INFO)
    with TestClient(tts_service.app) as client:
        response = client.post(
            "/clone",
            json={
                "video_path": "/abs/path/base.mp4",
                "text": "你好",
                "output_path": "/tmp/clone.wav",
                "ref_duration": 5.0,
                "asr_device": "cpu",
                "tts_device": "cpu",
            },
        )

    assert response.status_code == 500
    assert response.json()["detail"]["error"] == "TTS 执行失败: boom"
    assert any("stage=tts_clone_start" in record.getMessage() for record in caplog.records)
    assert any("stage=tts_clone_failed" in record.getMessage() for record in caplog.records)


def test_tts_service_clone_uses_env_default_devices(monkeypatch):
    captured = {}

    def fake_run_clone(**kwargs):
        captured.update(kwargs)
        return {
            "tts_audio_path": "/tmp/clone.wav",
            "voice_source": "clone",
            "fallback_used": False,
            "message": "ok",
        }

    monkeypatch.setenv("BS_MEDIA_TTS_ASR_DEVICE", "cuda:7")
    monkeypatch.setenv("BS_MEDIA_TTS_DEVICE", "cuda:6")
    monkeypatch.setattr(tts_service, "_run_clone", fake_run_clone)

    with TestClient(tts_service.app) as client:
        response = client.post(
            "/clone",
            json={
                "video_path": "/abs/path/base.mp4",
                "text": "你好",
                "output_path": "/tmp/clone.wav",
                "ref_duration": 5.0,
            },
        )

    assert response.status_code == 200
    assert captured["asr_device"] == "cuda:7"
    assert captured["tts_device"] == "cuda:6"


def test_tts_service_clone_rejects_non_prewarmed_devices(monkeypatch):
    monkeypatch.setenv("BS_MEDIA_TTS_ASR_DEVICE", "cuda:7")
    monkeypatch.setenv("BS_MEDIA_TTS_DEVICE", "cuda:6")

    with TestClient(tts_service.app) as client:
        response = client.post(
            "/clone",
            json={
                "video_path": "/abs/path/base.mp4",
                "text": "你好",
                "output_path": "/tmp/clone.wav",
                "ref_duration": 5.0,
                "asr_device": "cpu",
                "tts_device": "cpu",
            },
        )

    assert response.status_code == 500
    assert "仅支持预热后的 ASR 设备" in response.json()["detail"]["error"]


def test_tts_from_video_uses_injected_asr_resolver(monkeypatch, tmp_path):
    source_video = tmp_path / "video.mp4"
    source_video.write_bytes(b"video")
    output_path = tmp_path / "out.wav"
    captured = {}

    def fake_extract_reference_clip(
        video_path,
        output_dir,
        ref_duration=5.0,
        skip_ratio=0.05,
        max_attempts=5,
        asr_device="cuda:3",
        seed=None,
        asr_text_resolver=None,
    ):
        del skip_ratio, max_attempts, seed
        assert video_path == source_video.resolve()
        assert callable(asr_text_resolver)
        reference_clip = output_dir / "reference.wav"
        reference_clip.parent.mkdir(parents=True, exist_ok=True)
        reference_clip.write_bytes(b"clip")
        captured["resolver_text"] = asr_text_resolver(reference_clip)
        captured["ref_duration"] = ref_duration
        captured["asr_device"] = asr_device
        return reference_clip, "参考文本"

    def fake_synthesize_speech(*, reference_audio, ref_text, text, output_path, tts_device=None):
        del reference_audio, ref_text, text, tts_device
        output_path.write_bytes(b"audio")
        return output_path

    monkeypatch.setattr(tts_gen_sound, "extract_reference_clip", fake_extract_reference_clip)
    monkeypatch.setattr(tts_gen_sound, "synthesize_speech", fake_synthesize_speech)

    result = tts_gen_sound.tts_from_video(
        video_path=str(source_video),
        new_text="新的话语",
        output_path=output_path,
        asr_text_resolver=lambda path: f"resolved:{path.name}",
    )

    assert result == output_path
    assert captured == {
        "resolver_text": "resolved:reference.wav",
        "ref_duration": 5.0,
        "asr_device": "cuda:3",
    }
