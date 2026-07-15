from pathlib import Path

from platform_app.repositories.asr_repository import AsrRepository
from platform_app.repositories.lip_sync_repository import LipSyncTaskRepository
from platform_app.repositories.video_repository import VideoRepository
from phase3_algorithms.lip_sync_pipeline import (
    generate_script_candidates as pipeline_generate_script_candidates,
    poll_lip_sync_generation_with_output_dir as pipeline_poll_lip_sync_generation,
    regenerate_script_candidate as pipeline_regenerate_script_candidate,
    submit_lip_sync_generation as pipeline_submit_lip_sync_generation,
    validate_script_tts_duration_with_context,
)


class LipSyncGenerationAdapter:
    def __init__(self, *, db_path: Path, temp_dir: Path, generated_dir: Path):
        self.db_path = Path(db_path)
        self.temp_dir = Path(temp_dir)
        self.generated_dir = Path(generated_dir)
        self.video_repository = VideoRepository(self.db_path)
        self.asr_repository = AsrRepository(self.db_path)
        self.task_repository = LipSyncTaskRepository(self.db_path)

    def generate_script_candidates(
        self,
        *,
        base_video_path: str,
        base_video_asr_text: str,
        prompt_text: str,
        product_doc_text: str,
        count: int,
    ):
        return pipeline_generate_script_candidates(
            base_video_path=base_video_path,
            base_video_asr_text=base_video_asr_text,
            prompt_text=prompt_text,
            product_doc_text=product_doc_text,
            count=count,
        )

    def regenerate_script_candidate(
        self,
        *,
        base_video_path: str,
        base_video_asr_text: str,
        prompt_text: str,
        product_doc_text: str,
        source_script_text: str,
    ):
        return pipeline_regenerate_script_candidate(
            base_video_path=base_video_path,
            base_video_asr_text=base_video_asr_text,
            prompt_text=prompt_text,
            product_doc_text=product_doc_text,
            source_script_text=source_script_text,
        )

    def validate_script_tts_duration(self, *, base_video_path: str, script_text: str):
        video = self.video_repository.get_by_file_path(base_video_path)
        asr = self.asr_repository.get_by_video(video["id"]) if video else None
        return validate_script_tts_duration_with_context(
            base_video_duration_sec=float((video or {}).get("duration_sec") or 0.0),
            base_video_asr_text=str((asr or {}).get("full_text") or ""),
            script_text=script_text,
        )

    def submit_lip_sync_generation(
        self,
        *,
        task_id: str,
        base_video_path: str,
        script_text: str,
        aspect_mode: str,
        resolution: str,
        subtitle_enabled: bool,
        temp_dir: str,
        output_dir: str,
    ):
        return pipeline_submit_lip_sync_generation(
            task_id=task_id,
            base_video_path=base_video_path,
            script_text=script_text,
            aspect_mode=aspect_mode,
            resolution=resolution,
            subtitle_enabled=subtitle_enabled,
            temp_dir=temp_dir,
            output_dir=output_dir,
        )

    def poll_lip_sync_generation(self, *, task_id: str, video_job_id: str):
        return pipeline_poll_lip_sync_generation(
            task_id=task_id,
            video_job_id=video_job_id,
            output_dir=str((self.generated_dir / "lip_sync" / task_id / "final").resolve()),
        )

    def submit_generation(
        self,
        *,
        task_id: str,
        base_video_path: str,
        script_text: str,
        aspect_mode: str,
        resolution: str,
        subtitle_enabled: bool,
    ):
        return self.submit_lip_sync_generation(
            task_id=task_id,
            base_video_path=base_video_path,
            script_text=script_text,
            aspect_mode=aspect_mode,
            resolution=resolution,
            subtitle_enabled=subtitle_enabled,
            temp_dir=str((self.temp_dir / "lip_sync" / task_id).resolve()),
            output_dir=str((self.generated_dir / "lip_sync" / task_id / "final").resolve()),
        )

    def poll_generation(self, *, task_id: str, video_job_id: str):
        task = self.task_repository.get_task(task_id)
        if not video_job_id:
            return {"status": "failed", "message": "缺少有效的视频生成任务ID"}
        if task is None or str(task.get("video_job_id") or "") != video_job_id:
            return {"status": "failed", "message": "任务与视频生成作业不匹配"}
        return self.poll_lip_sync_generation(task_id=task_id, video_job_id=video_job_id)
