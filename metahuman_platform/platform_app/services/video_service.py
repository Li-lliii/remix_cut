import json
import shutil
import subprocess
import sys
import uuid
from pathlib import Path
from typing import Any

from platform_app.repositories.asr_repository import AsrRepository
from platform_app.repositories.video_repository import VideoRepository
from platform_app.services.asr_adapter import AsrAdapter, AsrAdapterError, infer_aspect_ratio, probe_duration

PROJECT_ROOT = Path(__file__).resolve().parents[3]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from utils.llm_client import call_llm


class VideoService:
    def __init__(self, *, db_path: Path, uploads_dir: Path | None = None, asr_adapter=None):
        self.db_path = Path(db_path)
        self.uploads_dir = Path(uploads_dir) if uploads_dir else None
        self.video_repository = VideoRepository(self.db_path)
        self.asr_repository = AsrRepository(self.db_path)
        self.asr_adapter = asr_adapter or AsrAdapter()

    def save_upload(self, *, role_id: str, filename: str, content: bytes):
        if not self.uploads_dir:
            raise RuntimeError("uploads_dir 未配置")

        video_id = str(uuid.uuid4())
        extension = Path(filename).suffix or ".mp4"
        target_dir = self.uploads_dir / "roles" / role_id / video_id
        try:
            target_dir.mkdir(parents=True, exist_ok=True)
            file_path = target_dir / f"source{extension}"
            file_path.write_bytes(content)

            duration_sec = probe_duration(file_path)
            aspect_ratio = infer_aspect_ratio(file_path)

            video = self.video_repository.create(
                video_id=video_id,
                role_id=role_id,
                title=filename,
                file_path=str(file_path),
                thumbnail_url="",
                duration_sec=duration_sec,
                aspect_ratio=aspect_ratio,
            )
            return video
        except Exception:
            shutil.rmtree(target_dir, ignore_errors=True)
            raise

    def _load_config(self) -> dict[str, Any]:
        config_path = PROJECT_ROOT / "config.yaml"
        if not config_path.exists():
            raise FileNotFoundError(f"配置文件不存在: {config_path}")
        try:
            import yaml  # type: ignore

            data = yaml.safe_load(config_path.read_text(encoding="utf-8"))
        except ModuleNotFoundError:
            command = [
                "conda",
                "run",
                "-n",
                "tts",
                "python",
                "-c",
                (
                    "import json, yaml, pathlib; "
                    f"path = pathlib.Path(r'''{config_path}'''); "
                    "print(json.dumps(yaml.safe_load(path.read_text(encoding='utf-8'))))"
                ),
            ]
            result = subprocess.run(command, capture_output=True, text=True, check=True)
            data = json.loads((result.stdout or "").strip().splitlines()[-1])
        if not isinstance(data, dict):
            raise ValueError(f"配置文件格式错误: {config_path}")
        return data

    def _get_asr_summary_llm_config(self) -> dict[str, Any]:
        llm_cfg = (self._load_config().get("llm") or {}).get("gen_word") or {}
        required = ["base_url", "api_key", "model", "timeout"]
        missing = [key for key in required if not llm_cfg.get(key)]
        if missing:
            raise ValueError(f"语音转文字总结失败: llm.gen_word 缺少必填项: {missing}")
        return {
            "base_url": str(llm_cfg["base_url"]),
            "api_key": str(llm_cfg["api_key"]),
            "model": str(llm_cfg["model"]),
            "timeout": int(llm_cfg["timeout"]),
            "temperature": float(llm_cfg.get("temperature", 0.3)),
            "top_p": float(llm_cfg.get("top_p", 0.9)),
            "max_tokens": int(llm_cfg["max_tokens"]) if llm_cfg.get("max_tokens") is not None else 256,
            "enable_thinking": bool(llm_cfg.get("enable_thinking", False)),
        }

    def _build_asr_summary_prompt(self, *, full_text: str) -> str:
        return (
            "你是视频语音转文字总结助手。请根据下面的识别文本生成一段中文总结。\n"
            "要求：\n"
            "1. 只输出总结正文，不要解释；\n"
            "2. 使用自然中文；\n"
            "3. 长度控制在100到200字；\n"
            "4. 保留关键信息和语义重点，不要逐字摘抄；\n"
            "5. 不要编造原文没有出现的信息。\n\n"
            f"识别文本：\n{full_text.strip()}"
        )

    def _generate_asr_summary(self, full_text: str) -> str:
        llm_cfg = self._get_asr_summary_llm_config()
        prompt = self._build_asr_summary_prompt(full_text=full_text)
        summary = call_llm(
            prompt=prompt,
            base_url=llm_cfg["base_url"],
            api_key=llm_cfg["api_key"],
            model=llm_cfg["model"],
            timeout=llm_cfg["timeout"],
            temperature=llm_cfg["temperature"],
            top_p=llm_cfg["top_p"],
            max_tokens=llm_cfg["max_tokens"],
            enable_thinking=llm_cfg["enable_thinking"],
        )
        summary = str(summary or "").strip()
        if not summary:
            raise RuntimeError("总结结果为空")
        return summary

    def process_video_asr(self, video_id: str):
        video = self.video_repository.get(video_id)
        if not video:
            return None

        self.video_repository.update_asr_status(video_id, "running")
        try:
            result = self.asr_adapter.transcribe(video_path=video["file_path"])
            full_text = result["full_text"].strip()
            segments = result["segments"]
            if not full_text or not segments:
                raise AsrAdapterError("ASR 结果不完整")
            self.asr_repository.upsert(
                role_video_id=video_id,
                full_text=full_text,
                segments=segments,
            )
            try:
                summary_text = self._generate_asr_summary(full_text)
                self.asr_repository.update_summary(
                    role_video_id=video_id,
                    summary_text=summary_text,
                )
            except Exception as exc:
                self.asr_repository.mark_summary_failed(
                    role_video_id=video_id,
                    error_message=str(exc),
                )
            return self.asr_repository.get_by_video(video_id)
        except Exception as exc:
            self.video_repository.update_asr_status(video_id, "failed", str(exc))
            return None
