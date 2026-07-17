"""测试 ComfyUI 换背景 API workflow 调用。

使用方式：
1. 确认 workstream/ai_transforms/replace_background_api.json 是 ComfyUI API 格式工作流。
2. 修改下面 VIDEO_PATH / BACKGROUND_PATH / SERVER_ADDRESS。
3. 运行：python metahuman_platform/test.py
"""

from __future__ import annotations

import json
import os
import argparse
import shutil
import uuid
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

import websocket  # pip install websocket-client


PROJECT_ROOT = Path(__file__).resolve().parents[1]

# ComfyUI 服务地址
SERVER_ADDRESS = "127.0.0.1:7040"

# API 格式工作流，不是 UI 格式工作流。
WORKFLOW_PATH = PROJECT_ROOT / "workstream" / "ai_transforms" / "replace_background_api.json"

# 输入文件。可以是本地绝对路径。
VIDEO_PATH = PROJECT_ROOT / "metahuman_platform" / "work" / "platform_uploads" / "input_shot.mp4"
BACKGROUND_PATH = PROJECT_ROOT / "metahuman_platform" / "work" / "platform_uploads" / "background.png"

# 当前 workflow 的 VHS_LoadVideo / LoadImage 节点读取 ComfyUI/input 下的文件名。
# 默认从根目录 config.yaml 的 comfyui.input_dir 读取，也可以用命令行 --input-dir 覆盖。
COMFYUI_INPUT_DIR: Path | None = None

# 当前 replace_background 工作流的关键节点。
VIDEO_NODE_ID = "178"
BACKGROUND_NODE_ID = "225"
OUTPUT_NODE_ID = "176"
SEED_NODE_ID = None  # 如果要改 seed，可填类似 "84"

client_id = str(uuid.uuid4())


def _load_default_comfy_input_dir() -> Path | None:
    config_path = PROJECT_ROOT / "config.yaml"
    if not config_path.exists():
        return None
    try:
        import yaml  # type: ignore

        config = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
        input_dir = ((config.get("comfyui") or {}).get("input_dir") or "").strip()
        return Path(input_dir).expanduser() if input_dir else None
    except Exception:
        return None


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="测试 ComfyUI 换背景 API workflow")
    parser.add_argument("--server", default=SERVER_ADDRESS, help="ComfyUI 服务地址，例如 127.0.0.1:7040")
    parser.add_argument("--workflow", default=str(WORKFLOW_PATH), help="API workflow JSON 路径")
    parser.add_argument("--video", default=str(VIDEO_PATH), help="输入视频本地路径")
    parser.add_argument("--background", default=str(BACKGROUND_PATH), help="背景图本地路径")
    parser.add_argument(
        "--input-dir",
        default=None,
        help="ComfyUI/input 目录；不传则读取 config.yaml 的 comfyui.input_dir",
    )
    parser.add_argument("--output-prefix", default=None, help="ComfyUI 输出 filename_prefix")
    return parser.parse_args()


def _load_workflow(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"工作流文件不存在: {path}")
    if path.stat().st_size == 0:
        raise ValueError(f"工作流文件为空，请导出 ComfyUI API workflow 后写入: {path}")
    workflow = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(workflow, dict):
        raise ValueError("工作流 JSON 顶层必须是对象")
    if "nodes" in workflow and "links" in workflow:
        raise ValueError(
            "当前文件看起来是 ComfyUI UI workflow，不是 API workflow。"
            "请在 ComfyUI 中导出 API 格式，或使用项目里的 run_comfyui_workflow.py 转换。"
        )
    return workflow


def _copy_to_comfy_input(source: Path, input_dir: Path) -> str:
    input_dir.mkdir(parents=True, exist_ok=True)
    target_name = f"{uuid.uuid4().hex[:8]}_{source.name}"
    target = input_dir / target_name
    shutil.copy2(source, target)
    return target_name


def _prepare_input_value(path: Path) -> str:
    if not path.exists():
        raise FileNotFoundError(f"输入文件不存在: {path}")
    if COMFYUI_INPUT_DIR is None:
        return str(path)
    return _copy_to_comfy_input(path, COMFYUI_INPUT_DIR)


def patch_workflow_inputs(
    workflow: dict[str, Any],
    *,
    video_value: str,
    background_value: str,
    filename_prefix: str,
) -> dict[str, Any]:
    """替换 API workflow 中的输入视频、背景图和输出前缀。"""
    prompt = json.loads(json.dumps(workflow))

    try:
        prompt[VIDEO_NODE_ID]["inputs"]["video"] = video_value
    except KeyError as exc:
        raise KeyError(f"未找到视频节点 {VIDEO_NODE_ID}.inputs.video") from exc

    try:
        prompt[BACKGROUND_NODE_ID]["inputs"]["image"] = background_value
    except KeyError as exc:
        raise KeyError(f"未找到背景图节点 {BACKGROUND_NODE_ID}.inputs.image") from exc

    try:
        prompt[OUTPUT_NODE_ID]["inputs"]["filename_prefix"] = filename_prefix
        prompt[OUTPUT_NODE_ID]["inputs"]["save_output"] = True
    except KeyError as exc:
        raise KeyError(f"未找到输出节点 {OUTPUT_NODE_ID}.inputs") from exc

    if SEED_NODE_ID and SEED_NODE_ID in prompt:
        prompt[SEED_NODE_ID]["inputs"]["seed"] = uuid.uuid4().int % (2**50)

    return prompt


def queue_prompt(prompt: dict[str, Any], prompt_id: str) -> dict[str, Any] | None:
    payload = {"prompt": prompt, "client_id": client_id, "prompt_id": prompt_id}
    data = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        f"http://{SERVER_ADDRESS}/prompt",
        data=data,
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(request) as response:
            return json.loads(response.read())
    except urllib.error.HTTPError as exc:
        print(f"HTTP Error {exc.code}: {exc.reason}")
        print(exc.read().decode("utf-8", errors="ignore"))
        return None


def get_history(prompt_id: str) -> dict[str, Any]:
    with urllib.request.urlopen(f"http://{SERVER_ADDRESS}/history/{prompt_id}") as response:
        return json.loads(response.read())


def download_output(filename: str, subfolder: str, folder_type: str) -> bytes:
    params = urllib.parse.urlencode(
        {
            "filename": filename,
            "subfolder": subfolder,
            "type": folder_type,
        }
    )
    with urllib.request.urlopen(f"http://{SERVER_ADDRESS}/view?{params}") as response:
        return response.read()


def wait_for_completion(prompt_id: str) -> dict[str, Any] | None:
    ws = websocket.WebSocket()
    ws.connect(f"ws://{SERVER_ADDRESS}/ws?clientId={client_id}")
    print("WebSocket 连接成功")

    try:
        while True:
            message = ws.recv()
            if not isinstance(message, str):
                continue
            payload = json.loads(message)
            message_type = payload.get("type")

            if message_type == "executing":
                data = payload.get("data") or {}
                if data.get("node") is None and data.get("prompt_id") == prompt_id:
                    print("执行完成")
                    break
                print(f"执行节点: {data.get('node')}")
            elif message_type == "progress":
                data = payload.get("data") or {}
                print(f"进度: {data.get('value', 0)}/{data.get('max', 0)}")
            elif message_type == "execution_error":
                print(f"执行错误: {json.dumps(payload, ensure_ascii=False)}")
                return None
    finally:
        ws.close()

    history = get_history(prompt_id)
    return history.get(prompt_id)


def save_outputs(history_data: dict[str, Any]) -> list[Path]:
    output_dir = PROJECT_ROOT / "output"
    output_dir.mkdir(parents=True, exist_ok=True)
    saved_paths: list[Path] = []

    for node_id, node_output in (history_data.get("outputs") or {}).items():
        for video in node_output.get("videos", []):
            print(f"下载视频: node={node_id} filename={video['filename']}")
            content = download_output(video["filename"], video.get("subfolder", ""), video.get("type", "output"))
            target = output_dir / video["filename"]
            target.write_bytes(content)
            saved_paths.append(target)
            print(f"已保存: {target}")

        for image in node_output.get("images", []):
            print(f"下载图像: node={node_id} filename={image['filename']}")
            content = download_output(image["filename"], image.get("subfolder", ""), image.get("type", "output"))
            target = output_dir / image["filename"]
            target.write_bytes(content)
            saved_paths.append(target)
            print(f"已保存: {target}")

    return saved_paths


def main() -> int:
    global SERVER_ADDRESS, COMFYUI_INPUT_DIR

    args = _parse_args()
    SERVER_ADDRESS = args.server
    workflow_path = Path(args.workflow).expanduser().resolve()
    video_path = Path(args.video).expanduser().resolve()
    background_path = Path(args.background).expanduser().resolve()
    COMFYUI_INPUT_DIR = Path(args.input_dir).expanduser().resolve() if args.input_dir else _load_default_comfy_input_dir()

    if COMFYUI_INPUT_DIR is None:
        print("未配置 ComfyUI input_dir。请在 config.yaml 配 comfyui.input_dir，或运行时传 --input-dir。")
        return 1

    print(f"ComfyUI: {SERVER_ADDRESS}")
    print(f"workflow: {workflow_path}")
    print(f"input_dir: {COMFYUI_INPUT_DIR}")
    print(f"video: {video_path}")
    print(f"background: {background_path}")

    workflow = _load_workflow(workflow_path)
    video_value = _prepare_input_value(video_path)
    background_value = _prepare_input_value(background_path)
    filename_prefix = args.output_prefix or f"ai_transform_test/{uuid.uuid4().hex[:8]}_replace_background"
    print(f"workflow video node value: {video_value}")
    print(f"workflow background node value: {background_value}")
    print(f"workflow output prefix: {filename_prefix}")

    prompt = patch_workflow_inputs(
        workflow,
        video_value=video_value,
        background_value=background_value,
        filename_prefix=filename_prefix,
    )

    prompt_id = str(uuid.uuid4())
    result = queue_prompt(prompt, prompt_id)
    if not result:
        print("任务提交失败")
        return 1

    print(f"任务已提交: {prompt_id}")
    history_data = wait_for_completion(prompt_id)
    if not history_data:
        print("任务执行失败")
        return 1

    saved = save_outputs(history_data)
    if not saved:
        print("任务完成，但没有找到可下载输出。请检查输出节点是否 save_output=True。")
        return 1

    print("测试完成")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
