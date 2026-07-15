import argparse
import json
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from utils.tts_gen_sound import tts_from_video


def main() -> int:
    parser = argparse.ArgumentParser(description="基于片段视频做 TTS 声音克隆")
    parser.add_argument("--video-path", required=True)
    parser.add_argument("--text", required=True)
    parser.add_argument("--output-path", required=True)
    parser.add_argument("--ref-duration", type=float, default=5.0)
    parser.add_argument("--asr-device", default="cuda:3")
    parser.add_argument("--tts-device", default="cuda:3")
    args = parser.parse_args()

    output_path = tts_from_video(
        video_path=args.video_path,
        new_text=args.text,
        output_path=Path(args.output_path).expanduser().resolve(),
        ref_duration=args.ref_duration,
        asr_device=args.asr_device,
        tts_device=args.tts_device,
    )
    print(
        json.dumps(
            {"tts_audio_path": str(Path(output_path).expanduser().resolve())},
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
