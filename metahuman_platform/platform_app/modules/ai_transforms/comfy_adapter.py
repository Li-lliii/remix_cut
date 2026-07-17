from __future__ import annotations

from pathlib import Path

from platform_app.services.algorithm_http_client import AlgorithmHttpClient
from platform_app.settings import get_settings


DEFAULT_REPLACE_BACKGROUND_OVERRIDES = {
    "178.inputs.video": "{video}",
    "225.inputs.image": "{background_image}",
    "176.inputs.filename_prefix": "{filename_prefix}",
    "176.inputs.save_output": True,
}


class AiTransformComfyAdapter:
    def __init__(self):
        settings = get_settings()
        self.client = AlgorithmHttpClient(
            base_url=settings.comfy_service_base_url,
            service_name="AI变身视频生成",
            connect_timeout_sec=settings.algo_connect_timeout_sec,
            read_timeout_sec=settings.algo_read_timeout_sec,
        )

    def submit_replace_background(
        self,
        *,
        task_id: str,
        source_video_path: str | Path,
        background_image_path: str | Path,
        output_dir: str | Path,
        params: dict | None = None,
    ) -> dict:
        workflow_params = dict(params or {})
        workflow_params.setdefault("node_overrides", DEFAULT_REPLACE_BACKGROUND_OVERRIDES)
        payload = self.client.post_json(
            "/jobs",
            json={
                "task_id": task_id,
                "task_type": "replace_background",
                "workflow_name": "ai_transform_replace_background",
                "video_path": str(Path(source_video_path).expanduser().resolve()),
                "background_image_path": str(Path(background_image_path).expanduser().resolve()),
                "output_dir": str(Path(output_dir).expanduser().resolve()),
                "params": workflow_params,
            },
        )
        prompt_id = str(payload.get("prompt_id") or "").strip()
        if not prompt_id:
            raise RuntimeError(f"ComfyUI 未返回 prompt_id: {payload}")
        return {"backend_job_id": prompt_id, "raw": payload}

    def poll(self, backend_job_id: str) -> dict:
        return self.client.get_json(f"/jobs/{backend_job_id}")
