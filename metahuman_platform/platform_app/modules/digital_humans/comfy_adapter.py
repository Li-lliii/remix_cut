from __future__ import annotations

from pathlib import Path

from platform_app.services.algorithm_http_client import AlgorithmHttpClient
from platform_app.settings import get_settings


class DigitalHumanComfyAdapter:
    def __init__(self):
        settings = get_settings()
        self.settings = settings
        self.client = AlgorithmHttpClient(
            base_url=settings.comfy_service_base_url,
            service_name="数字人训练",
            connect_timeout_sec=settings.algo_connect_timeout_sec,
            read_timeout_sec=settings.algo_read_timeout_sec,
        )

    def submit_avatar_training(self, *, task: dict, assets: list[dict]) -> dict:
        asset_map = {asset["asset_type"]: asset for asset in assets}
        talking_video = asset_map.get("talking_video")
        if talking_video is None:
            raise ValueError("数字人训练缺少 talking_video 素材")

        voice_sample = asset_map.get("voice_sample")
        audio_path = (voice_sample or talking_video)["file_path"]
        output_dir = self.settings.generated_dir / "digital_humans" / task["id"]
        output_dir.mkdir(parents=True, exist_ok=True)

        payload = self.client.post_json(
            "/jobs",
            json={
                "task_id": task["id"],
                "task_type": "material_avatar_build",
                "video_path": str(Path(talking_video["file_path"]).expanduser().resolve()),
                "audio_path": str(Path(audio_path).expanduser().resolve()),
                "output_dir": str(output_dir.resolve()),
            },
        )
        prompt_id = str(payload.get("prompt_id") or "").strip()
        if not prompt_id:
            raise RuntimeError("ComfyUI 未返回 prompt_id")
        return {"backend_job_id": prompt_id, "raw": payload}

