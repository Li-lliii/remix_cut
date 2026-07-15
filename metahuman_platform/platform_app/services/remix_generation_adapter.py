from pathlib import Path

from phase2_algorithms.remix_pipeline import (
    generate_remix_output,
    poll_remix_video_job,
    submit_generate_remix_output,
)


class RemixGenerationAdapter:
    def __init__(self, *, temp_dir: Path, generated_dir: Path):
        self.temp_dir = Path(temp_dir)
        self.generated_dir = Path(generated_dir)

    def generate(
        self,
        *,
        task_id: str,
        item_id: str,
        segment_file_path: str,
        segment_asr_text: str,
        prompt_text: str,
        product_doc_text: str,
        aspect_mode: str,
        resolution: str,
        subtitle_enabled: bool,
    ):
        audio_dir = self.temp_dir / "remix" / task_id
        video_dir = self.generated_dir / "remix" / task_id
        audio_dir.mkdir(parents=True, exist_ok=True)
        video_dir.mkdir(parents=True, exist_ok=True)
        return generate_remix_output(
            task_id=task_id,
            task_item_id=item_id,
            segment_video_path=segment_file_path,
            segment_asr_text=segment_asr_text,
            product_prompt=prompt_text,
            product_doc_text=product_doc_text,
            aspect_mode=aspect_mode,
            resolution=resolution,
            subtitle_enabled=subtitle_enabled,
            temp_dir=str(audio_dir),
            output_dir=str(video_dir),
        )

    def submit_generation(
        self,
        *,
        task_id: str,
        item_id: str,
        segment_file_path: str,
        segment_asr_text: str,
        prompt_text: str,
        product_doc_text: str,
        aspect_mode: str,
        resolution: str,
        subtitle_enabled: bool,
    ):
        audio_dir = self.temp_dir / "remix" / task_id
        video_dir = self.generated_dir / "remix" / task_id
        audio_dir.mkdir(parents=True, exist_ok=True)
        video_dir.mkdir(parents=True, exist_ok=True)
        return submit_generate_remix_output(
            task_id=task_id,
            task_item_id=item_id,
            segment_video_path=segment_file_path,
            segment_asr_text=segment_asr_text,
            product_prompt=prompt_text,
            product_doc_text=product_doc_text,
            aspect_mode=aspect_mode,
            resolution=resolution,
            subtitle_enabled=subtitle_enabled,
            temp_dir=str(audio_dir),
            output_dir=str(video_dir),
        )

    def poll_generation(self, *, task_id: str, prompt_id: str):
        video_dir = self.generated_dir / "remix" / task_id
        video_dir.mkdir(parents=True, exist_ok=True)
        return poll_remix_video_job(
            prompt_id=prompt_id,
            output_dir=str(video_dir),
        )
