from pathlib import Path

from phase2_algorithms import build_remix_segments


class PreprocessAdapter:
    def __init__(self, *, work_dir: Path):
        self.work_dir = Path(work_dir)

    def build_segments(self, *, video_id: str, video_path: str, asr_full_text: str, asr_segments: list[dict]):
        output_dir = self.work_dir / "generated" / "preprocess" / video_id / "segments"
        output_dir.mkdir(parents=True, exist_ok=True)
        return build_remix_segments(
            video_id=video_id,
            video_path=video_path,
            asr_full_text=asr_full_text,
            asr_segments=asr_segments,
            output_dir=str(output_dir),
        )
