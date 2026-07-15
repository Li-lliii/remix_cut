from __future__ import annotations

from contextlib import asynccontextmanager
import os
from pathlib import Path
from typing import Any
import logging
import time

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


class TranscribeRequest(BaseModel):
    video_path: str = Field(..., description="视频绝对路径")
    device: str | None = Field(default=None, description="推理设备")
    segment_seconds: int = Field(default=60, ge=1, description="切分时长")


class TranscribeAudioRequest(BaseModel):
    audio_path: str = Field(..., description="音频绝对路径")
    device: str | None = Field(default=None, description="推理设备")


_SERVICE_STATE: dict[str, Any] = {
    "model_loaded": False,
    "warmup_error": None,
}


def _default_asr_device() -> str:
    return str(os.environ.get("BS_MEDIA_ASR_DEVICE", "cuda:0"))


def _visible_devices() -> str:
    return str(os.environ.get("CUDA_VISIBLE_DEVICES", ""))


def _backend_ready() -> bool:
    return bool(_SERVICE_STATE.get("model_loaded"))


def _warmup_backend() -> None:
    try:
        from utils.asr_detect_word import _get_asr_model, _get_vad_model
    except Exception as exc:
        _SERVICE_STATE["model_loaded"] = False
        _SERVICE_STATE["warmup_error"] = f"无法导入算法 ASR: {exc}"
        raise RuntimeError(str(_SERVICE_STATE["warmup_error"])) from exc

    device = _default_asr_device()
    try:
        _get_asr_model(device)
        _get_vad_model(device)
    except Exception as exc:
        _SERVICE_STATE["model_loaded"] = False
        _SERVICE_STATE["warmup_error"] = f"ASR 预热失败: {exc}"
        raise RuntimeError(str(_SERVICE_STATE["warmup_error"])) from exc

    _SERVICE_STATE["model_loaded"] = True
    _SERVICE_STATE["warmup_error"] = None


def _ensure_backend_ready() -> None:
    if _backend_ready():
        return
    _warmup_backend()


def _normalize_asr_result(result: Any, *, video_path: str) -> dict[str, Any]:
    if isinstance(result, dict):
        return {
            "full_text": str(result.get("full_text") or ""),
            "segments": list(result.get("segments") or []),
        }

    if isinstance(result, str):
        return {
            "full_text": result,
            "segments": [
                {
                    "start_sec": 0.0,
                    "end_sec": 0.0,
                    "text": result,
                }
            ],
        }

    raise RuntimeError(f"ASR 返回了不支持的结果类型: {type(result).__name__}")


def _run_asr(*, video_path: str, device: str | None, segment_seconds: int) -> dict[str, Any]:
    _ensure_backend_ready()
    try:
        from utils.asr_detect_word import detect_video_word
    except Exception as exc:
        raise RuntimeError(f"无法导入算法 ASR: {exc}") from exc

    try:
        result = detect_video_word(
            video_path,
            segment_seconds=segment_seconds,
            device=device or _default_asr_device(),
        )
    except Exception as exc:
        raise RuntimeError(f"ASR 执行失败: {exc}") from exc

    payload = _normalize_asr_result(result, video_path=video_path)
    if not payload["full_text"].strip():
        raise RuntimeError("ASR 结果为空")
    return payload


def _normalize_transcribe_audio_result(result: Any) -> dict[str, Any]:
    if isinstance(result, dict):
        text = str(result.get("text") or result.get("full_text") or "").strip()
        return {"text": text}
    if isinstance(result, str):
        return {"text": result.strip()}
    raise RuntimeError(f"ASR 音频返回了不支持的结果类型: {type(result).__name__}")


def _run_transcribe_audio(*, audio_path: str, device: str | None) -> dict[str, Any]:
    _ensure_backend_ready()
    resolved_path = Path(audio_path).expanduser().resolve()
    if not resolved_path.exists():
        raise RuntimeError(f"音频文件不存在: {resolved_path}")

    try:
        import soundfile as sf
    except Exception as exc:
        raise RuntimeError(f"无法导入音频读取依赖: {exc}") from exc

    try:
        from utils.asr_detect_word import _asr_segment, _get_asr_model
    except Exception as exc:
        raise RuntimeError(f"无法导入算法 ASR: {exc}") from exc

    try:
        audio_data, samplerate = sf.read(str(resolved_path))
    except Exception as exc:
        raise RuntimeError(f"音频解析失败: {exc}") from exc

    if hasattr(audio_data, "ndim") and int(getattr(audio_data, "ndim")) != 1:
        raise RuntimeError("音频必须是单声道")

    model = _get_asr_model(device or _default_asr_device())
    try:
        text = _asr_segment(model, audio_data, samplerate)
    except Exception as exc:
        raise RuntimeError(f"ASR 执行失败: {exc}") from exc

    payload = _normalize_transcribe_audio_result(text)
    if not payload["text"].strip():
        raise RuntimeError("ASR 结果为空")
    return payload


def create_app() -> FastAPI:
    @asynccontextmanager
    async def lifespan(_: FastAPI):
        _ensure_backend_ready()
        yield

    app = FastAPI(title="BS Media ASR Service", lifespan=lifespan)

    @app.get("/health")
    def health() -> dict[str, str]:
        return {
            "status": "ok",
            "default_device": _default_asr_device(),
            "visible_devices": _visible_devices(),
        }

    @app.get("/ready")
    def ready() -> dict[str, Any]:
        return {
            "status": "ready",
            "model_loaded": _backend_ready(),
            "default_device": _default_asr_device(),
            "visible_devices": _visible_devices(),
        }

    @app.post("/transcribe-audio")
    def transcribe_audio(payload: TranscribeAudioRequest) -> dict[str, Any]:
        resolved_device = payload.device or _default_asr_device()
        started_at = time.perf_counter()
        logger.info(
            "stage=asr_transcribe_audio_start audio_path=%s device=%s visible_devices=%s",
            payload.audio_path,
            resolved_device,
            _visible_devices(),
        )
        try:
            result = _run_transcribe_audio(
                audio_path=payload.audio_path,
                device=resolved_device,
            )
            elapsed_ms = (time.perf_counter() - started_at) * 1000.0
            logger.info(
                "stage=asr_transcribe_audio_success elapsed_ms=%.1f text_len=%s",
                elapsed_ms,
                len(str(result.get("text") or "")),
            )
            return result
        except Exception as exc:
            elapsed_ms = (time.perf_counter() - started_at) * 1000.0
            logger.exception(
                "stage=asr_transcribe_audio_failed elapsed_ms=%.1f error=%s",
                elapsed_ms,
                str(exc),
            )
            raise HTTPException(status_code=500, detail={"error": str(exc)}) from exc

    @app.post("/transcribe")
    def transcribe(payload: TranscribeRequest) -> dict[str, Any]:
        resolved_device = payload.device or _default_asr_device()
        started_at = time.perf_counter()
        logger.info(
            "stage=asr_transcribe_start video_path=%s device=%s segment_seconds=%s visible_devices=%s",
            payload.video_path,
            resolved_device,
            payload.segment_seconds,
            _visible_devices(),
        )
        try:
            result = _run_asr(
                video_path=payload.video_path,
                device=resolved_device,
                segment_seconds=payload.segment_seconds,
            )
            elapsed_ms = (time.perf_counter() - started_at) * 1000.0
            logger.info(
                "stage=asr_transcribe_success elapsed_ms=%.1f full_text_len=%s segments=%s",
                elapsed_ms,
                len(str(result.get("full_text") or "")),
                len(list(result.get("segments") or [])),
            )
            return result
        except Exception as exc:
            elapsed_ms = (time.perf_counter() - started_at) * 1000.0
            logger.exception(
                "stage=asr_transcribe_failed elapsed_ms=%.1f error=%s",
                elapsed_ms,
                str(exc),
            )
            raise HTTPException(status_code=500, detail={"error": str(exc)}) from exc

    return app


app = create_app()
