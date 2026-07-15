import json
import os
import subprocess
from pathlib import Path

from platform_app.services.algorithm_http_client import AlgorithmHttpClient
from platform_app.services.tts_adapter import TtsAdapter


PROJECT_ROOT = Path(__file__).resolve().parents[2]
REMIX_ROOT = PROJECT_ROOT
if str(REMIX_ROOT) not in __import__("sys").path:
    __import__("sys").path.insert(0, str(REMIX_ROOT))


def _get_default_voice_path() -> Path:
    return Path(__file__).resolve().parents[1] / "assets" / "default_voice" / "dongbei_clone_5s.wav"


def _get_comfy_mode() -> str:
    return os.environ.get("BS_MEDIA_COMFY_MODE", "legacy")


def _get_tts_adapter() -> TtsAdapter:
    return TtsAdapter(
        service_base_url=os.environ.get("BS_MEDIA_TTS_SERVICE_BASE_URL", "http://127.0.0.1:7001"),
        connect_timeout_sec=float(os.environ.get("BS_MEDIA_ALGO_CONNECT_TIMEOUT_SEC", "10")),
        read_timeout_sec=float(
            os.environ.get(
                "BS_MEDIA_ALGO_READ_TIMEOUT_SEC",
                os.environ.get("BS_MEDIA_ALGO_HTTP_TIMEOUT_SEC", "600"),
            )
        ),
    )


def _get_comfy_client() -> AlgorithmHttpClient:
    return AlgorithmHttpClient(
        base_url=os.environ.get("BS_MEDIA_COMFY_SERVICE_BASE_URL", "http://127.0.0.1:7002"),
        service_name="视频生成",
        connect_timeout_sec=float(os.environ.get("BS_MEDIA_ALGO_CONNECT_TIMEOUT_SEC", "10")),
        read_timeout_sec=float(
            os.environ.get(
                "BS_MEDIA_ALGO_READ_TIMEOUT_SEC",
                os.environ.get("BS_MEDIA_ALGO_HTTP_TIMEOUT_SEC", "600"),
            )
        ),
    )


def _generate_tts_from_video(*, base_video_path: str, script_text: str, task_id: str, temp_dir: str) -> str:
    output_path = Path(temp_dir).expanduser().resolve() / "tts" / f"{task_id}.wav"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    return _get_tts_adapter().clone_from_video(
        video_path=str(Path(base_video_path).expanduser().resolve()),
        text=script_text,
        output_path=str(output_path),
    )


def _generate_tts_from_default_voice(*, script_text: str, task_id: str, temp_dir: str) -> str:
    default_voice_path = _get_default_voice_path()
    if not default_voice_path.exists():
        raise RuntimeError("默认参考音色不存在，无法执行静音视频兜底")
    output_path = Path(temp_dir).expanduser().resolve() / "tts" / f"{task_id}.wav"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    ref_text = _get_default_voice_reference_text(default_voice_path)
    return _get_tts_adapter().synthesize_default(
        text=script_text,
        output_path=str(output_path),
        reference_audio_path=str(default_voice_path.resolve()),
        reference_text=ref_text,
    )


def _get_default_voice_reference_text(reference_audio: Path) -> str:
    sidecar_path = reference_audio.with_suffix(".txt")
    if sidecar_path.exists():
        return sidecar_path.read_text(encoding="utf-8").strip()
    return "这是默认东北女声参考音色，用于静音视频兜底合成。"


def generate_tts_with_fallback(*, base_video_path: str, script_text: str, task_id: str, temp_dir: str) -> str:
    try:
        return _generate_tts_from_video(
            base_video_path=base_video_path,
            script_text=script_text,
            task_id=task_id,
            temp_dir=temp_dir,
        )
    except Exception:
        return _generate_tts_from_default_voice(
            script_text=script_text,
            task_id=task_id,
            temp_dir=temp_dir,
        )


def submit_comfyui_job(
    *,
    task_id: str,
    base_video_path: str,
    tts_audio_path: str,
    output_dir: str,
    aspect_mode: str,
    resolution: str,
    subtitle_enabled: bool,
) -> str:
    del aspect_mode, resolution, subtitle_enabled
    #有两种调用 ComfyUI 的方式
    if _get_comfy_mode() == "service":#请求 ComfyUI 网关服务，网关服务拿到后，再提交给真正的 ComfyUI。
        payload = _get_comfy_client().post_json(
            "/jobs",
            json={
                "task_id": task_id,
                "task_type": "lip_sync",
                "video_path": str(Path(base_video_path).expanduser().resolve()),
                "audio_path": str(Path(tts_audio_path).expanduser().resolve()),
                "output_dir": str(Path(output_dir).expanduser().resolve()),
            },
        )
        return str(payload.get("prompt_id") or "").strip()
    #直接启动脚本
    command = [
        "python",
        str(PROJECT_ROOT / "scripts" / "run_comfyui_video.py"),
        "--action",
        "submit",
        "--video-path",
        str(Path(base_video_path).expanduser().resolve()),
        "--audio-path",
        str(Path(tts_audio_path).expanduser().resolve()),
        "--output-dir",
        str(Path(output_dir).expanduser().resolve()),
    ]
    result = subprocess.run(command, capture_output=True, text=True, check=True)
    payload = json.loads((result.stdout or "").strip().splitlines()[-1])
    return str(payload.get("prompt_id") or "").strip()


def _resolve_poll_output_dir(*, task_id: str, output_dir: str | None = None) -> Path:
    if output_dir:
        return Path(output_dir).expanduser().resolve()
    generated_root = os.environ.get("BS_MEDIA_GENERATED_DIR")
    if generated_root:
        return Path(generated_root).expanduser().resolve() / "lip_sync" / task_id / "final"
    return Path.cwd().resolve() / "generated" / "lip_sync" / task_id / "final"


def poll_comfyui_job(*, task_id: str, video_job_id: str, output_dir: str | None = None) -> dict:
    if _get_comfy_mode() == "service":
        payload = _get_comfy_client().get_json(f"/jobs/{video_job_id}")
        if payload.get("status") == "success":
            return {
                "status": "success",
                "output_video_url": str(Path(payload["output_video_url"]).expanduser().resolve()),
            }
        if payload.get("status") == "pending":
            return {"status": "pending"}
        return {"status": "failed", "message": str(payload.get("message") or "视频生成状态异常")}
    resolved_output_dir = _resolve_poll_output_dir(task_id=task_id, output_dir=output_dir)
    command = [
        "python",
        str(PROJECT_ROOT / "scripts" / "run_comfyui_video.py"),
        "--action",
        "poll",
        "--prompt-id",
        video_job_id,
        "--output-dir",
        str(resolved_output_dir),
    ]
    result = subprocess.run(command, capture_output=True, text=True, check=True)
    payload = json.loads((result.stdout or "").strip().splitlines()[-1])
    if payload.get("status") == "success":
        return {
            "status": "success",
            "output_video_url": str(Path(payload["output_video_url"]).expanduser().resolve()),
        }
    if payload.get("status") == "pending":
        return {"status": "pending"}
    return {"status": "failed", "message": str(payload.get("message") or "视频生成状态异常")}
