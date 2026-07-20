from __future__ import annotations

import argparse
import json
import random
import sys
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from utils.gen_video import ComfyUIClient


def _load_comfy_config() -> dict[str, Any]:
    import yaml

    config_path = PROJECT_ROOT / "config.yaml"
    config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    return dict(config.get("comfyui") or {})


def _set_nested(workflow: dict[str, Any], dotted_path: str, value: Any) -> None:
    parts = dotted_path.split(".")
    if len(parts) < 3:
        raise ValueError(f"node override 路径无效: {dotted_path}")
    current: Any = workflow
    for part in parts[:-1]:
        if part not in current:
            raise KeyError(f"工作流中不存在节点路径: {dotted_path}")
        current = current[part]
    current[parts[-1]] = value


def _convert_ui_workflow_to_api(workflow: dict[str, Any]) -> dict[str, Any]:
    links = {
        int(link[0]): [str(link[1]), int(link[2])]
        for link in workflow.get("links", [])
        if isinstance(link, list) and len(link) >= 3
    }
    prompt: dict[str, Any] = {}
    for node in workflow.get("nodes", []):
        node_id = str(node.get("id"))
        class_type = node.get("type")
        if not node_id or not class_type or class_type == "Note":
            continue

        inputs: dict[str, Any] = {}
        widgets = node.get("widgets_values")
        widget_index = 0
        for item in node.get("inputs", []) or []:
            name = item.get("name")
            if not name:
                continue
            link_id = item.get("link")
            if link_id is not None:
                source = links.get(int(link_id))
                if source is not None:
                    inputs[name] = source
                continue

            if isinstance(widgets, dict) and name in widgets:
                inputs[name] = widgets[name]
            elif isinstance(widgets, list) and widget_index < len(widgets):
                inputs[name] = widgets[widget_index]
                widget_index += 1

        prompt[node_id] = {
            "class_type": class_type,
            "inputs": inputs,
        }
    return prompt


def _load_workflow_prompt(workflow_path: str) -> dict[str, Any]:
    workflow = json.loads(Path(workflow_path).expanduser().read_text(encoding="utf-8"))
    if isinstance(workflow, dict) and "nodes" in workflow and "links" in workflow:
        return _convert_ui_workflow_to_api(workflow)
    return workflow


def _render_value(value: Any, variables: dict[str, Any]) -> Any:
    if isinstance(value, str):
        rendered = value
        for key, replacement in variables.items():
            rendered = rendered.replace("{" + key + "}", str(replacement))
        return rendered
    return value


def prepare_workflow(
    *,
    workflow_path: str,
    video_filename: str,
    background_filename: str,
    output_prefix: str,
    params: dict[str, Any],
) -> dict[str, Any]:
    workflow = _load_workflow_prompt(workflow_path)
    variables = {
        "video": video_filename,
        "background_image": background_filename,
        "filename_prefix": output_prefix,
        "seed": random.randint(0, 2**50 - 1),
    }
    overrides = params.get("node_overrides") or {}
    if not isinstance(overrides, dict) or not overrides:
        raise ValueError("换背景工作流缺少 params.node_overrides 节点映射")
    for dotted_path, raw_value in overrides.items():
        _set_nested(workflow, str(dotted_path), _render_value(raw_value, variables))
    return workflow


def submit_workflow(
    *,
    workflow_path: str,
    workflow_name: str,
    video_path: str,
    background_image_path: str,
    output_dir: str,
    params: dict[str, Any] | None = None,
) -> str:
    comfy_cfg = _load_comfy_config()
    comfy_cfg["workflow_path"] = str(Path(workflow_path).expanduser().resolve())
    comfy_cfg["output_dir"] = str(Path(output_dir).expanduser().resolve())
    client = ComfyUIClient(comfy_cfg)
    video_filename = client.copy_to_comfyui_input(video_path)
    background_filename = client.copy_to_comfyui_input(background_image_path)
    output_prefix = f"ai_transforms/{workflow_name}/{Path(output_dir).name}"
    workflow = prepare_workflow(
        workflow_path=str(Path(workflow_path).expanduser().resolve()),
        video_filename=video_filename,
        background_filename=background_filename,
        output_prefix=output_prefix,
        params=params or {},
    )
    result = client.queue_prompt(workflow)
    prompt_id = str(result.get("prompt_id") or "").strip()
    if not prompt_id:
        raise RuntimeError(f"ComfyUI 未返回 prompt_id: {result}")
    return prompt_id


def main() -> int:
    parser = argparse.ArgumentParser(description="提交通用 ComfyUI 工作流")
    parser.add_argument("--workflow-path", required=True)
    parser.add_argument("--workflow-name", default="ai_transform_replace_background")
    parser.add_argument("--video-path", required=True)
    parser.add_argument("--background-image-path", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--params-json", default="{}")
    args = parser.parse_args()
    prompt_id = submit_workflow(
        workflow_path=args.workflow_path,
        workflow_name=args.workflow_name,
        video_path=args.video_path,
        background_image_path=args.background_image_path,
        output_dir=args.output_dir,
        params=json.loads(args.params_json or "{}"),
    )
    print(json.dumps({"status": "submitted", "prompt_id": prompt_id}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
