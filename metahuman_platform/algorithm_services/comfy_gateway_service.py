from __future__ import annotations

import os
import uuid
import logging
from pathlib import Path
from typing import Any, Callable

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from .comfy_job_store import ComfyJobStore

logger = logging.getLogger(__name__)


class SubmitRequest(BaseModel):
    video_path: str = Field(..., description="原始视频路径")
    audio_path: str | None = Field(default=None, description="音频路径")
    background_image_path: str | None = Field(default=None, description="换背景参考图路径")
    output_dir: str = Field(..., description="输出目录")
    task_type: str | None = Field(default="lip_sync")
    task_id: str | None = Field(default=None)
    workflow_name: str | None = Field(default=None)
    params: dict[str, Any] = Field(default_factory=dict)


def _default_job_store() -> ComfyJobStore:
    store_path = os.environ.get(
        "BS_MEDIA_COMFY_JOB_STORE_PATH",
        str(Path(__file__).resolve().parents[1] / "work" / "comfy_gateway_jobs.json"),
    )
    return ComfyJobStore(Path(store_path))


def _config_path() -> Path:
    env_path = os.environ.get("BS_MEDIA_CONFIG_PATH")
    if env_path:
        return Path(env_path).expanduser().resolve()
    return Path(__file__).resolve().parents[2] / "config.yaml"


def _load_comfy_config() -> dict[str, Any]:
    import yaml

    config = yaml.safe_load(_config_path().read_text(encoding="utf-8"))
    return dict(config.get("comfyui") or {})


def _default_workflow_path(*, env_key: str, filename: str) -> str:
    return str(
        Path(
            os.environ.get(
                env_key,
                str(Path(__file__).resolve().parents[2] / "workstream" / "ai_transforms" / filename),
            )
        )
        .expanduser()
        .resolve()
    )


def _backend_ready() -> bool:
    try:
        from utils.gen_video import ComfyUIClient

        comfy_cfg = _load_comfy_config()
        comfy_cfg.setdefault(
            "workflow_path",
            _default_workflow_path(
                env_key="BS_MEDIA_REPLACE_SPEECH_WORKFLOW_PATH",
                filename="replace_speech_api.json",
            ),
        )
        client = ComfyUIClient(comfy_cfg)
        return bool(client.check_health())
    except Exception:
        return False


def _submit_to_underlying_job(
    *,
    video_path: str,
    audio_path: str | None,
    output_dir: str,
    task_type: str | None = None,
    task_id: str | None = None,
    background_image_path: str | None = None,
    workflow_name: str | None = None,
    params: dict[str, Any] | None = None,
) -> str:
    del task_id
    if task_type == "replace_background":
        return _submit_replace_background_job(
            video_path=video_path,
            background_image_path=background_image_path,
            output_dir=output_dir,
            workflow_name=workflow_name,
            params=params or {},
        )
    if not audio_path:
        raise RuntimeError("视频生成服务提交失败: audio_path 不能为空")
    try:
        comfy_cfg = _load_comfy_config()
        comfy_cfg["workflow_path"] = _default_workflow_path(
            env_key="BS_MEDIA_REPLACE_SPEECH_WORKFLOW_PATH",
            filename="replace_speech_api.json",
        )
        comfy_cfg["output_dir"] = str(Path(output_dir).expanduser().resolve())
        from utils.gen_video import ComfyUIClient

        client = ComfyUIClient(comfy_cfg)
        return client.submit_job(video_path, audio_path)
    except Exception as exc:
        raise RuntimeError(f"视频生成服务提交失败: {exc}") from exc


def _submit_replace_background_job(
    *,
    video_path: str,
    background_image_path: str | None,
    output_dir: str,
    workflow_name: str | None = None,
    params: dict[str, Any] | None = None,
) -> str:
    if not background_image_path:
        raise RuntimeError("换背景任务缺少 background_image_path")
    try:
        import uuid

        from scripts.comfyui import replace_background_api_workflow as replace_background_workflow

        comfy_cfg = _load_comfy_config()
        server_address = str(comfy_cfg.get("server_address") or "").strip()
        input_dir = str(comfy_cfg.get("input_dir") or "").strip()
        if not server_address:
            raise RuntimeError("config.yaml 缺少 comfyui.server_address")
        if not input_dir:
            raise RuntimeError("config.yaml 缺少 comfyui.input_dir")
        workflow_path = _default_workflow_path(
            env_key="BS_MEDIA_REPLACE_BACKGROUND_WORKFLOW_PATH",
            filename="replace_background_api.json",
        )
        replace_background_workflow.SERVER_ADDRESS = server_address
        replace_background_workflow.COMFYUI_INPUT_DIR = Path(input_dir).expanduser().resolve()

        workflow = replace_background_workflow._load_workflow(Path(workflow_path))
        video_value = replace_background_workflow._prepare_input_value(Path(video_path).expanduser().resolve())
        background_value = replace_background_workflow._prepare_input_value(
            Path(background_image_path).expanduser().resolve()
        )
        filename_prefix = (
            str((params or {}).get("filename_prefix") or "").strip()
            or f"ai_transforms/{workflow_name or 'ai_transform_replace_background'}/{Path(output_dir).name}"
        )
        prompt = replace_background_workflow.patch_workflow_inputs(
            workflow,
            video_value=video_value,
            background_value=background_value,
            filename_prefix=filename_prefix,
        )
        prompt_id = str(uuid.uuid4())
        result = replace_background_workflow.queue_prompt(prompt, prompt_id)
        if not result:
            raise RuntimeError("ComfyUI /prompt 未返回有效结果，请查看 comfyui-gateway 日志")
        return prompt_id
    except Exception as exc:
        raise RuntimeError(f"换背景视频生成服务提交失败: {exc}") from exc


def _poll_underlying_job(*, prompt_id: str, output_dir: str, task_type: str | None = None) -> dict[str, Any]:
    try:
        comfy_cfg = _load_comfy_config()
        if task_type == "replace_background":
            comfy_cfg["workflow_path"] = _default_workflow_path(
                env_key="BS_MEDIA_REPLACE_BACKGROUND_WORKFLOW_PATH",
                filename="replace_background_api.json",
            )
        else:
            comfy_cfg["workflow_path"] = _default_workflow_path(
                env_key="BS_MEDIA_REPLACE_SPEECH_WORKFLOW_PATH",
                filename="replace_speech_api.json",
            )
        comfy_cfg["output_dir"] = str(Path(output_dir).expanduser().resolve())
        from utils.gen_video import ComfyUIClient

        client = ComfyUIClient(comfy_cfg)
        history = client.get_history(prompt_id)
    except Exception as exc:
        raise RuntimeError(f"视频生成服务轮询失败: {exc}") from exc

    if prompt_id not in history:
        return {"status": "pending"}

    task_data = history[prompt_id]
    status = str(task_data.get("status", {}).get("status_str") or "").lower()
    if status in {"success", "completed"}:
        output_path = client.extract_output_video(task_data)
        if output_path:
            return {
                "status": "success",
                "output_video_url": str(Path(output_path).expanduser().resolve()),
            }
        return {"status": "failed", "message": "无法找到输出视频"}
    if status in {"pending", "running", "queued", "executing", "started", "processing"}:
        return {"status": "pending"}
    if status in {"error", "failed"}:
        return {
            "status": "failed",
            "message": task_data.get("node_errors", {}) or "任务失败",
        }
    return {"status": "pending"}


def create_app(
    *,
    job_store: ComfyJobStore | None = None,
    submitter: Callable[..., str] | None = None,
    poller: Callable[..., dict[str, Any]] | None = None,
    ready_checker: Callable[[], bool] | None = None,
) -> FastAPI:
    store = job_store or _default_job_store()
    submit_impl = submitter or _submit_to_underlying_job
    poll_impl = poller or _poll_underlying_job
    ready_impl = ready_checker or _backend_ready

    app = FastAPI(title="BS Media ComfyUI Gateway Service")

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/ready")
    def ready() -> dict[str, Any]:
        return {"status": "ready", "comfyui_reachable": ready_impl()}

    @app.post("/jobs")
    def submit_job(payload: SubmitRequest) -> dict[str, Any]:
        try:
            logger.info(
                (
                    "stage=comfy_submit_start task_id=%s task_type=%s video_path=%s "
                    "audio_path=%s background_image_path=%s output_dir=%s"
                ),
                payload.task_id,
                payload.task_type,
                payload.video_path,
                payload.audio_path,
                payload.background_image_path,
                payload.output_dir,
            )
            prompt_id = submit_impl(
                video_path=payload.video_path,
                audio_path=payload.audio_path,
                output_dir=payload.output_dir,
                task_type=payload.task_type,
                task_id=payload.task_id,
                background_image_path=payload.background_image_path,
                workflow_name=payload.workflow_name,
                params=payload.params,
            )
            if not prompt_id:
                raise RuntimeError("视频生成服务提交失败: 未返回 prompt_id")
            logger.info("stage=comfy_submit_success prompt_id=%s task_id=%s", prompt_id, payload.task_id)
            store.save_job(
                {
                    "prompt_id": prompt_id,
                    "video_path": payload.video_path,
                    "audio_path": payload.audio_path,
                    "background_image_path": payload.background_image_path,
                    "output_dir": str(Path(payload.output_dir).expanduser().resolve()),
                    "task_type": payload.task_type,
                    "task_id": payload.task_id,
                    "workflow_name": payload.workflow_name,
                    "status": "submitted",
                    "message": "submitted",
                }
            )
            return {"status": "submitted", "prompt_id": prompt_id}
        except Exception as exc:
            logger.exception("stage=comfy_submit_failed error=%s", str(exc))
            raise HTTPException(status_code=500, detail={"error": str(exc)}) from exc

    @app.get("/jobs/{prompt_id}")
    def poll_job(prompt_id: str) -> dict[str, Any]:
        record = store.get_job(prompt_id)
        if record is None:
            raise HTTPException(status_code=404, detail={"error": "任务不存在"})
        try:
            logger.info(
                "stage=comfy_poll_start prompt_id=%s task_id=%s",
                prompt_id,
                record.get("task_id"),
            )
            result = poll_impl(
                prompt_id=prompt_id,
                output_dir=str(record["output_dir"]),
                task_type=str(record.get("task_type") or ""),
            )
            if result["status"] == "pending":
                logger.info("stage=comfy_poll_pending prompt_id=%s", prompt_id)
                store.update_job(prompt_id, status="pending", message="pending")
                return {"status": "pending"}
            if result["status"] == "success":
                output_video_url = str(Path(result["output_video_url"]).expanduser().resolve())
                logger.info("stage=comfy_poll_success prompt_id=%s output_video_url=%s", prompt_id, output_video_url)
                store.update_job(
                    prompt_id,
                    status="success",
                    output_video_url=output_video_url,
                    message="success",
                )
                return {"status": "success", "output_video_url": output_video_url}
            message = str(result.get("message") or "生成失败")
            logger.error("stage=comfy_poll_failed prompt_id=%s message=%s", prompt_id, message)
            store.update_job(prompt_id, status="failed", message=message)
            return {"status": "failed", "message": message}
        except Exception as exc:
            logger.exception("stage=comfy_poll_exception prompt_id=%s error=%s", prompt_id, str(exc))
            store.update_job(prompt_id, status="failed", message=str(exc))
            raise HTTPException(status_code=500, detail={"error": str(exc)}) from exc

    return app


app = create_app()
