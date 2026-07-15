from __future__ import annotations

from pathlib import Path


class FakePreprocessAdapter:
    def __init__(self, base_dir: Path):
        self.base_dir = Path(base_dir)

    def build_segments(self, *, video_id: str, video_path: str, asr_full_text: str, asr_segments: list[dict]):
        del video_path, asr_full_text
        output_dir = self.base_dir / "generated" / "preprocess" / video_id / "segments"
        output_dir.mkdir(parents=True, exist_ok=True)
        results = []
        for index, segment in enumerate(asr_segments, start=1):
            segment_id = f"segment-{index}"
            clip_path = output_dir / f"{segment_id}.mp4"
            clip_path.write_bytes(b"clip")
            results.append(
                {
                    "segment_id": segment_id,
                    "start_sec": segment["start_sec"],
                    "end_sec": segment["end_sec"],
                    "duration_sec": segment["end_sec"] - segment["start_sec"],
                    "asr_text": segment["text"],
                    "segment_file_path": str(clip_path.resolve()),
                }
            )
        return results


class FakeGenerationAdapter:
    def __init__(self, temp_dir: Path, generated_dir: Path):
        self.temp_dir = Path(temp_dir)
        self.generated_dir = Path(generated_dir)
        self.jobs = {}

    def _build_paths(self, task_id: str, item_id: str):
        audio_dir = self.temp_dir / "remix" / task_id
        video_dir = self.generated_dir / "remix" / task_id
        audio_dir.mkdir(parents=True, exist_ok=True)
        video_dir.mkdir(parents=True, exist_ok=True)
        audio_path = audio_dir / f"{item_id}.wav"
        video_path = video_dir / f"{item_id}.mp4"
        return audio_path, video_path

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
        del segment_file_path, product_doc_text, aspect_mode, resolution, subtitle_enabled
        audio_path, video_path = self._build_paths(task_id, item_id)
        audio_path.write_bytes(b"tts")
        prompt_id = f"prompt-{item_id}"
        self.jobs[prompt_id] = {
            "video_path": video_path,
            "content": f"{prompt_text}|{segment_asr_text}".encode("utf-8"),
            "poll_count": 0,
        }
        return {
            "rewritten_text": f"改写：{prompt_text}",
            "tts_audio_path": str(audio_path.resolve()),
            "prompt_id": prompt_id,
        }

    def poll_generation(self, *, task_id: str, prompt_id: str):
        del task_id
        job = self.jobs[prompt_id]
        job["poll_count"] += 1
        if job["poll_count"] == 1:
            return {"status": "pending", "prompt_id": prompt_id}
        job["video_path"].write_bytes(job["content"])
        return {
            "status": "success",
            "prompt_id": prompt_id,
            "output_video_url": str(job["video_path"].resolve()),
        }

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
        submitted = self.submit_generation(
            task_id=task_id,
            item_id=item_id,
            segment_file_path=segment_file_path,
            segment_asr_text=segment_asr_text,
            prompt_text=prompt_text,
            product_doc_text=product_doc_text,
            aspect_mode=aspect_mode,
            resolution=resolution,
            subtitle_enabled=subtitle_enabled,
        )
        result = self.poll_generation(task_id=task_id, prompt_id=submitted["prompt_id"])
        result = self.poll_generation(task_id=task_id, prompt_id=submitted["prompt_id"])
        return {
            "rewritten_text": submitted["rewritten_text"],
            "tts_audio_path": submitted["tts_audio_path"],
            "output_video_url": result["output_video_url"],
        }


class FakeLipSyncGenerationAdapter:
    def __init__(self, temp_dir: Path, generated_dir: Path, *, estimated_duration: float = 12.5):
        self.temp_dir = Path(temp_dir)
        self.generated_dir = Path(generated_dir)
        self.estimated_duration = estimated_duration
        self.jobs = {}
        self.regenerate_count = 0

    def generate_script_candidates(
        self,
        *,
        base_video_path: str,
        base_video_asr_text: str,
        prompt_text: str,
        product_doc_text: str,
        count: int,
    ):
        del base_video_path, base_video_asr_text, product_doc_text
        return [
            {
                "content": f"{prompt_text}-候选文案-{index}",
                "char_count": 10 + index,
                "estimated_tts_duration_sec": 8.0 + index,
            }
            for index in range(1, count + 1)
        ]

    def regenerate_script_candidate(
        self,
        *,
        base_video_path: str,
        base_video_asr_text: str,
        prompt_text: str,
        product_doc_text: str,
        source_script_text: str,
    ):
        del base_video_path, base_video_asr_text, product_doc_text
        self.regenerate_count += 1
        return {
            "content": f"{prompt_text}-类似一版-{self.regenerate_count}-{source_script_text}",
            "char_count": len(source_script_text) + 8,
            "estimated_tts_duration_sec": 11.2,
        }

    def validate_script_tts_duration(self, *, base_video_path: str, script_text: str):
        del base_video_path, script_text
        return {
            "estimated_tts_duration_sec": self.estimated_duration,
            "valid": self.estimated_duration <= 30.0,
        }

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
        del base_video_path, aspect_mode, resolution, subtitle_enabled
        audio_dir = self.temp_dir / "lip_sync" / task_id
        audio_dir.mkdir(parents=True, exist_ok=True)
        audio_path = audio_dir / "tts.wav"
        audio_path.write_text(script_text, encoding="utf-8")
        job_id = f"job-{task_id}"
        self.jobs[job_id] = {"task_id": task_id, "script_text": script_text, "poll_count": 0}
        return {
            "final_script_text": script_text,
            "tts_audio_path": str(audio_path.resolve()),
            "video_job_id": job_id,
        }

    def poll_generation(self, *, task_id: str, video_job_id: str):
        job = self.jobs[video_job_id]
        assert job["task_id"] == task_id
        job["poll_count"] += 1
        if job["poll_count"] == 1:
            return {"status": "pending"}
        output_dir = self.generated_dir / "lip_sync" / task_id / "final"
        output_dir.mkdir(parents=True, exist_ok=True)
        output_path = output_dir / f"{task_id}.mp4"
        output_path.write_text(job["script_text"], encoding="utf-8")
        return {
            "status": "success",
            "output_video_url": str(output_path.resolve()),
        }
