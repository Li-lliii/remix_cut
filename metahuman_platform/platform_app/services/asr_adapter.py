import os
import shutil
import subprocess
from pathlib import Path

import httpx

from platform_app.services.algorithm_errors import AlgorithmServiceProtocolError
from platform_app.services.algorithm_http_client import AlgorithmHttpClient


class AsrAdapterError(RuntimeError):
    """ASR 适配失败。"""


class AsrAdapter:
    def __init__(
        self,
        mode: str = "service",
        *,
        service_base_url: str | None = None,
        connect_timeout_sec: float = 10.0,
        read_timeout_sec: float = 600.0,
        transport: httpx.BaseTransport | None = None,
    ):
        self.mode = mode
        self.service_base_url = service_base_url or os.environ.get(
            "BS_MEDIA_ASR_SERVICE_BASE_URL",
            "http://127.0.0.1:7000",
        )
        self.connect_timeout_sec = connect_timeout_sec
        self.read_timeout_sec = read_timeout_sec
        self.transport = transport

    def transcribe(self, *, video_path: str, device: str | None = None, segment_seconds: int = 60):
        if self.mode == "mock":
            return self._mock_result(video_path)

        if self.mode == "service":
            try:
                result = self._service_result(video_path, device=device, segment_seconds=segment_seconds)
                if not result["full_text"].strip():
                    raise AsrAdapterError("ASR 结果为空")
                return result
            except Exception as exc:
                raise AsrAdapterError(str(exc)) from exc

        raise AsrAdapterError(f"不支持的 ASR 模式: {self.mode}")

    def _service_result(self, video_path: str, device: str | None, segment_seconds: int):
        client = AlgorithmHttpClient(
            base_url=self.service_base_url,
            service_name="ASR",
            connect_timeout_sec=self.connect_timeout_sec,
            read_timeout_sec=self.read_timeout_sec,
            transport=self.transport,
        )
        request_payload = {
            "video_path": str(Path(video_path).expanduser().resolve()),
            "segment_seconds": segment_seconds,
        }
        resolved_device = device or os.environ.get("BS_MEDIA_ASR_DEVICE")
        if resolved_device:
            request_payload["device"] = resolved_device
        payload = client.post_json(
            "/transcribe",
            json=request_payload,
        )
        full_text = payload.get("full_text", "")
        segments = payload.get("segments")
        if not isinstance(full_text, str) or not isinstance(segments, list):
            raise AlgorithmServiceProtocolError("ASR 服务返回结构异常: 缺少 full_text 或 segments")
        return {
            "full_text": full_text,
            "segments": segments,
        }

    def _mock_result(self, video_path: str):
        path = Path(video_path)
        duration_sec = probe_duration(path)
        text = f"模拟ASR结果：{path.stem}"
        return {
            "full_text": text,
            "segments": [{"start_sec": 0.0, "end_sec": duration_sec, "text": text}],
        }


def probe_duration(video_path: Path) -> float:
    ffprobe = shutil.which("ffprobe")
    if not ffprobe or not video_path.exists():
        return 0.0

    command = [
        ffprobe,
        "-v",
        "error",
        "-show_entries",
        "format=duration",
        "-of",
        "default=noprint_wrappers=1:nokey=1",
        str(video_path),
    ]
    result = subprocess.run(command, capture_output=True, text=True, check=False)
    if result.returncode != 0:
        return 0.0
    try:
        return float(result.stdout.strip() or 0.0)
    except ValueError:
        return 0.0


def infer_aspect_ratio(video_path: Path) -> str:
    ffprobe = shutil.which("ffprobe")
    if not ffprobe or not video_path.exists():
        return "unknown"

    command = [
        ffprobe,
        "-v",
        "error",
        "-select_streams",
        "v:0",
        "-show_entries",
        "stream=width,height",
        "-of",
        "csv=s=x:p=0",
        str(video_path),
    ]
    result = subprocess.run(command, capture_output=True, text=True, check=False)
    if result.returncode != 0:
        return "unknown"

    payload = result.stdout.strip()
    if "x" not in payload:
        return "unknown"
    width, height = payload.split("x", 1)
    if width.isdigit() and height.isdigit() and int(height) > 0:
        return f"{width}:{height}"
    return "unknown"
