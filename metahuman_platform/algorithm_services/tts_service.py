from __future__ import annotations

import os
import json
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any
import logging
import time
from urllib import request as urllib_request
from urllib.error import HTTPError, URLError

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

import utils.tts_gen_sound as tts_backend

logger = logging.getLogger(__name__)

_SERVICE_READY = False


class CloneRequest(BaseModel):
    video_path: str = Field(..., description="参考视频路径")
    text: str = Field(..., description="待合成文本")
    output_path: str = Field(..., description="输出音频路径")
    ref_duration: float = Field(default=5.0, ge=0.1)
    asr_device: str | None = Field(default=None)
    tts_device: str | None = Field(default=None)


class DefaultRequest(BaseModel):
    text: str = Field(..., description="待合成文本")
    output_path: str = Field(..., description="输出音频路径")
    reference_audio_path: str | None = Field(default=None, description="默认参考音色")
    reference_text: str | None = Field(default=None, description="参考文本")


def _default_voice_path() -> Path:
    return Path(__file__).resolve().parents[1] / "assets" / "default_voice" / "dongbei_clone_5s.wav"


def _default_voice_text(reference_audio: Path) -> str:
    sidecar = reference_audio.with_suffix(".txt")
    if sidecar.exists():
        return sidecar.read_text(encoding="utf-8").strip()
    return "这是默认东北女声参考音色，用于静音视频兜底合成。"


def _backend_ready() -> bool:
    return _SERVICE_READY and tts_backend.is_tts_model_loaded()


def _default_voice_ready() -> bool:
    return _default_voice_path().exists()


def _default_tts_asr_device() -> str:
    return str(os.environ.get("BS_MEDIA_TTS_ASR_DEVICE", "cuda:0"))


def _default_tts_device() -> str:
    return str(os.environ.get("BS_MEDIA_TTS_DEVICE", "cuda:0"))


def _asr_service_base_url() -> str:
    configured = os.environ.get("BS_MEDIA_ASR_SERVICE_BASE_URL")
    if configured:
        return str(configured).rstrip("/")
    host = str(os.environ.get("BS_MEDIA_ASR_SERVICE_HOST", os.environ.get("BS_MEDIA_ALGO_HOST", "127.0.0.1")))
    port = str(os.environ.get("BS_MEDIA_ASR_SERVICE_PORT", "7000"))
    return f"http://{host}:{port}".rstrip("/")


def _visible_devices() -> str:
    return str(os.environ.get("CUDA_VISIBLE_DEVICES", ""))


def _asr_service_ready() -> bool:
    try:
        with urllib_request.urlopen(f"{_asr_service_base_url()}/ready", timeout=5) as response:
            body = response.read().decode("utf-8")
    except Exception:
        return False

    try:
        payload = json.loads(body)
    except json.JSONDecodeError:
        return False

    return (
        isinstance(payload, dict)
        and payload.get("status") == "ready"
        and payload.get("model_loaded") is True
    )


def _post_json(url: str, payload: dict[str, Any]) -> dict[str, Any]:
    data = json.dumps(payload).encode("utf-8")
    request = urllib_request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib_request.urlopen(request, timeout=600) as response:
            body = response.read().decode("utf-8")
    except HTTPError as exc:
        body = exc.read().decode("utf-8", errors="ignore")
        raise RuntimeError(f"ASR 服务请求失败: HTTP {exc.code}: {body}") from exc
    except URLError as exc:
        raise RuntimeError(f"ASR 服务请求失败: {exc}") from exc

    try:
        decoded = json.loads(body)
    except json.JSONDecodeError as exc:
        raise RuntimeError("ASR 服务返回了非 JSON 响应") from exc

    if not isinstance(decoded, dict):
        raise RuntimeError("ASR 服务返回结构异常: 顶层不是对象")
    return decoded


def _transcribe_reference_audio_via_asr_service(
    *,
    audio_path: Path,
    device: str | None,
) -> str:
    payload: dict[str, Any] = {
        "audio_path": str(Path(audio_path).expanduser().resolve()),
    }
    if device:
        payload["device"] = device

    response = _post_json(f"{_asr_service_base_url()}/transcribe-audio", payload)
    text = str(response.get("text") or "").strip()
    if not text:
        raise RuntimeError("ASR 服务返回空文本")
    return text


def _warmup_tts_backend() -> None:
    global _SERVICE_READY
    tts_backend.warmup_tts_model(device=_default_tts_device())
    _SERVICE_READY = True


def _ensure_service_ready() -> None:
    if not _backend_ready():
        raise RuntimeError("TTS 模型未完成预热")
    if not _default_voice_ready():
        raise RuntimeError(f"默认参考音色不存在: {_default_voice_path()}")
    if not _asr_service_ready():
        raise RuntimeError("ASR 服务未就绪")


def _ensure_requested_devices_supported(*, asr_device: str, tts_device: str) -> None:
    default_asr_device = _default_tts_asr_device()
    default_tts_device = _default_tts_device()
    if asr_device != default_asr_device:
        raise RuntimeError(
            f"当前 TTS 服务仅支持预热后的 ASR 设备: request={asr_device}, default={default_asr_device}"
        )
    if tts_device != default_tts_device:
        raise RuntimeError(
            f"当前 TTS 服务仅支持预热后的 TTS 设备: request={tts_device}, default={default_tts_device}"
        )


def _run_clone(
    *,
    video_path: str,
    text: str,
    output_path: str,
    ref_duration: float,
    asr_device: str,
    tts_device: str,
) -> dict[str, Any]:
    try:
        result = tts_backend.tts_from_video(
            video_path=video_path,
            new_text=text,
            output_path=Path(output_path).expanduser().resolve(),
            ref_duration=ref_duration,
            asr_device=asr_device,
            tts_device=tts_device,
            asr_text_resolver=lambda clip_path: _transcribe_reference_audio_via_asr_service(
                audio_path=clip_path,
                device=asr_device,
            ),
        )
    except Exception as exc:
        raise RuntimeError(f"TTS 执行失败: {exc}") from exc

    output_file = Path(result).expanduser().resolve()
    return {
        "tts_audio_path": str(output_file),
        "voice_source": "clone",
        "fallback_used": False,
        "message": "ok",
    }


def _run_default(
    *,
    text: str,
    output_path: str,
    reference_audio_path: str | None = None,
    reference_text: str | None = None,
) -> dict[str, Any]:
    reference_audio = Path(reference_audio_path).expanduser().resolve() if reference_audio_path else _default_voice_path()
    if not reference_audio.exists():
        raise RuntimeError(f"默认参考音色不存在: {reference_audio}")

    ref_text = reference_text.strip() if reference_text else _default_voice_text(reference_audio)

    try:
        result = tts_backend.synthesize_speech(
            reference_audio=reference_audio,
            ref_text=ref_text,
            text=text,
            output_path=Path(output_path).expanduser().resolve(),
        )
    except Exception as exc:
        raise RuntimeError(f"TTS 执行失败: {exc}") from exc

    output_file = Path(result).expanduser().resolve()
    return {
        "tts_audio_path": str(output_file),
        "voice_source": "default",
        "fallback_used": True,
        "message": "used default reference voice",
    }


@asynccontextmanager
async def _lifespan(app: FastAPI):
    del app
    _warmup_tts_backend()
    _ensure_service_ready()
    yield


def create_app() -> FastAPI:
    app = FastAPI(title="BS Media TTS Service", lifespan=_lifespan)

    @app.get("/health")
    def health() -> dict[str, str]:
        return {
            "status": "ok",
            "default_asr_device": _default_tts_asr_device(),
            "default_tts_device": _default_tts_device(),
            "visible_devices": _visible_devices(),
        }

    @app.get("/ready")
    def ready() -> dict[str, Any]:
        model_loaded = _backend_ready() and _default_voice_ready() and _asr_service_ready()
        return {
            "status": "ready",
            "model_loaded": model_loaded,
            "default_voice_available": _default_voice_ready(),
            "default_asr_device": _default_tts_asr_device(),
            "default_tts_device": _default_tts_device(),
            "visible_devices": _visible_devices(),
        }

    @app.post("/clone")
    def clone(payload: CloneRequest) -> dict[str, Any]:
        resolved_asr_device = payload.asr_device or _default_tts_asr_device()
        resolved_tts_device = payload.tts_device or _default_tts_device()
        started_at = time.perf_counter()
        logger.info(
            "stage=tts_clone_start video_path=%s asr_device=%s tts_device=%s output_path=%s visible_devices=%s",
            payload.video_path,
            resolved_asr_device,
            resolved_tts_device,
            payload.output_path,
            _visible_devices(),
        )
        try:
            _ensure_requested_devices_supported(
                asr_device=resolved_asr_device,
                tts_device=resolved_tts_device,
            )
            _ensure_service_ready()
            result = _run_clone(
                video_path=payload.video_path,
                text=payload.text,
                output_path=payload.output_path,
                ref_duration=payload.ref_duration,
                asr_device=resolved_asr_device,
                tts_device=resolved_tts_device,
            )
            elapsed_ms = (time.perf_counter() - started_at) * 1000.0
            logger.info(
                "stage=tts_clone_success elapsed_ms=%.1f tts_audio_path=%s",
                elapsed_ms,
                result.get("tts_audio_path"),
            )
            return result
        except Exception as exc:
            elapsed_ms = (time.perf_counter() - started_at) * 1000.0
            logger.exception(
                "stage=tts_clone_failed elapsed_ms=%.1f error=%s",
                elapsed_ms,
                str(exc),
            )
            raise HTTPException(status_code=500, detail={"error": str(exc)}) from exc

    @app.post("/synthesize-default")
    def synthesize_default(payload: DefaultRequest) -> dict[str, Any]:
        started_at = time.perf_counter()
        logger.info(
            "stage=tts_default_start output_path=%s",
            payload.output_path,
        )
        try:
            result = _run_default(
                text=payload.text,
                output_path=payload.output_path,
                reference_audio_path=payload.reference_audio_path,
                reference_text=payload.reference_text,
            )
            elapsed_ms = (time.perf_counter() - started_at) * 1000.0
            logger.info(
                "stage=tts_default_success elapsed_ms=%.1f tts_audio_path=%s",
                elapsed_ms,
                result.get("tts_audio_path"),
            )
            return result
        except Exception as exc:
            elapsed_ms = (time.perf_counter() - started_at) * 1000.0
            logger.exception(
                "stage=tts_default_failed elapsed_ms=%.1f error=%s",
                elapsed_ms,
                str(exc),
            )
            raise HTTPException(status_code=500, detail={"error": str(exc)}) from exc

    return app


app = create_app()
