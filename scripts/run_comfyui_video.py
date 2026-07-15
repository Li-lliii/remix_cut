import argparse
import json
import sys
from pathlib import Path

import yaml


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from utils.gen_video import ComfyUIClient


def main() -> int:
    parser = argparse.ArgumentParser(description="调用 ComfyUI 生成最终混剪视频")
    parser.add_argument("--action", choices=["submit", "poll"], default="submit")
    parser.add_argument("--video-path")
    parser.add_argument("--audio-path")
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--prompt-id")
    args = parser.parse_args()

    config_path = PROJECT_ROOT / "config.yaml"
    with config_path.open("r", encoding="utf-8") as handle:
        config = yaml.safe_load(handle)
    comfy_cfg = dict(config.get("comfyui") or {})
    comfy_cfg["output_dir"] = str(Path(args.output_dir).expanduser().resolve())

    client = ComfyUIClient(comfy_cfg)
    if args.action == "submit":
        if not args.video_path or not args.audio_path:
            raise ValueError("submit 模式必须提供 --video-path 和 --audio-path")
        result = client.submit_video_job(args.video_path, args.audio_path)
    else:
        if not args.prompt_id:
            raise ValueError("poll 模式必须提供 --prompt-id")
        result = client.poll_video_job(args.prompt_id)

    payload = {"status": result["status"], "prompt_id": result.get("prompt_id")}
    if result.get("output_path"):
        payload["output_video_url"] = str(Path(str(result["output_path"])).expanduser().resolve())
    if result.get("message"):
        payload["message"] = result["message"]
    print(json.dumps(payload, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
