from __future__ import annotations

import os
from pathlib import Path

import httpx

from platform_app.services.algorithm_http_client import AlgorithmHttpClient
from platform_app.services.algorithm_errors import AlgorithmServiceProtocolError


class TtsAdapterError(RuntimeError):
    """TTS 适配失败。"""


class TtsAdapter:
    def __init__(
        self,
        *,
        service_base_url: str | None = None,
        connect_timeout_sec: float = 10.0,
        read_timeout_sec: float = 600.0,
        transport: httpx.BaseTransport | None = None,
    ):
        self.service_base_url = service_base_url or os.environ.get(
            "BS_MEDIA_TTS_SERVICE_BASE_URL",
            "http://127.0.0.1:7001",
        )
        self.connect_timeout_sec = connect_timeout_sec
        self.read_timeout_sec = read_timeout_sec
        self.transport = transport

    def clone_from_video(
        self,
        *,
        video_path: str,
        text: str,
        output_path: str,
        ref_duration: float = 5.0,
        asr_device: str | None = None,
        tts_device: str | None = None,
    ) -> str:
        payload = {
            "video_path": str(Path(video_path).expanduser().resolve()),
            "text": text,
            "output_path": str(Path(output_path).expanduser().resolve()),
            "ref_duration": float(ref_duration),
        }
        if asr_device is not None:
            payload["asr_device"] = asr_device
        if tts_device is not None:
            payload["tts_device"] = tts_device

        result = self._post_json("/clone", payload, service_name="TTS")
        return self._resolve_tts_audio_path(result)

    def synthesize_default(
        self,
        *,
        text: str,
        output_path: str,
        reference_audio_path: str | None = None,
        reference_text: str | None = None,
    ) -> str:
        payload = {
            "text": text,
            "output_path": str(Path(output_path).expanduser().resolve()),
        }
        if reference_audio_path is not None:
            payload["reference_audio_path"] = str(Path(reference_audio_path).expanduser().resolve())
        if reference_text is not None:
            payload["reference_text"] = reference_text

        result = self._post_json("/synthesize-default", payload, service_name="TTS")
        return self._resolve_tts_audio_path(result)

    def _post_json(self, path: str, payload: dict, *, service_name: str) -> dict:
        client = AlgorithmHttpClient(
            base_url=self.service_base_url,
            service_name=service_name,
            connect_timeout_sec=self.connect_timeout_sec,
            read_timeout_sec=self.read_timeout_sec,
            transport=self.transport,
        )
        try:
            result = client.post_json(path, json=payload)
        except AlgorithmServiceProtocolError:
            raise
        except Exception as exc:
            raise TtsAdapterError(str(exc)) from exc
        if not isinstance(result, dict):
            raise TtsAdapterError("TTS 服务返回结构异常: 顶层不是对象")
        return result

    def _resolve_tts_audio_path(self, payload: dict) -> str:
        audio_path = payload.get("tts_audio_path")
        if not isinstance(audio_path, str) or not audio_path.strip():
            raise TtsAdapterError("TTS 服务返回结构异常: 缺少 tts_audio_path")
        return str(Path(audio_path).expanduser().resolve())
