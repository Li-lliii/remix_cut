import json
import os
import re
import subprocess
import sys
import uuid
from pathlib import Path
from typing import Any

from platform_app.services.algorithm_http_client import AlgorithmHttpClient
from platform_app.services.tts_adapter import TtsAdapter


REMIX_ROOT = Path(__file__).resolve().parents[2]
if str(REMIX_ROOT) not in sys.path:
    sys.path.insert(0, str(REMIX_ROOT))


def _get_comfy_mode() -> str:
    return os.environ.get("BS_MEDIA_COMFY_MODE", "legacy")


def _get_tts_adapter() -> TtsAdapter:
    return TtsAdapter(
        service_base_url=os.environ.get("BS_MEDIA_TTS_SERVICE_BASE_URL", "http://127.0.0.1:7001"),
        connect_timeout_sec=float(os.environ.get("BS_MEDIA_ALGO_CONNECT_TIMEOUT_SEC", "10")),
        read_timeout_sec=float(
            os.environ.get(
                "BS_MEDIA_ALGO_READ_TIMEOUT_SEC",
                os.environ.get("BS_MEDIA_ALGO_HTTP_TIMEOUT_SEC", "600"),
            )
        ),
    )


def _get_comfy_client() -> AlgorithmHttpClient:
    '''
    获取ComfyUI服务的HTTP客户端，用于修改超时时间
    '''
    return AlgorithmHttpClient(
        base_url=os.environ.get("BS_MEDIA_COMFY_SERVICE_BASE_URL", "http://127.0.0.1:7002"),
        service_name="视频生成",
        connect_timeout_sec=float(os.environ.get("BS_MEDIA_ALGO_CONNECT_TIMEOUT_SEC", "10")),
        read_timeout_sec=float(
            os.environ.get(
                "BS_MEDIA_ALGO_READ_TIMEOUT_SEC",
                os.environ.get("BS_MEDIA_ALGO_HTTP_TIMEOUT_SEC", "600"),
            )
        ),
    )


def cut_video_clip(*, video_path: str, start_sec: float, end_sec: float, output_path: str) -> str:
    '''
    根据asr识别出来的起始和结束位置，使用ffmpeg对视频进行切分
    '''
    source = Path(video_path).expanduser().resolve()
    target = Path(output_path).expanduser().resolve()
    if not source.exists():
        raise FileNotFoundError(f"视频读取失败: 原视频不存在: {source}")
    if end_sec < start_sec:
        raise ValueError(f"视频切片失败: 时间区间无效 start={start_sec}, end={end_sec}")

    target.parent.mkdir(parents=True, exist_ok=True)
    duration_sec = max(end_sec - start_sec, 0.0)
    command = [
        "ffmpeg",
        "-y",
        "-i",
        str(source),
        "-ss",
        f"{start_sec:.3f}",
        "-t",
        f"{duration_sec:.3f}",
        "-map",
        "0:v:0",
        "-map",
        "0:a:0?",
        "-c:v",
        "libx264",
        "-preset",
        "veryfast",
        "-crf",
        "18",
        "-pix_fmt",
        "yuv420p",
        "-c:a",
        "aac",
        "-b:a",
        "192k",
        "-fflags",
        "+genpts",
        "-avoid_negative_ts",
        "make_zero",
        "-movflags",
        "+faststart",
        str(target),
    ]
    try:
        subprocess.run(command, check=True, capture_output=True)
    except subprocess.CalledProcessError as exc:
        stderr = exc.stderr.decode(errors="ignore") if exc.stderr else ""
        raise RuntimeError(f"视频切片失败: ffmpeg 执行失败, {stderr}") from exc

    if not target.exists():
        raise RuntimeError(f"视频切片失败: 未生成切片文件: {target}")
    return str(target)


def concat_video_clips(*, clip_paths: list[str], output_path: str) -> str:
    '''
    将多个已经切好的视频片段按顺序拼接成一个最终视频
    '''
    if not clip_paths:
        raise ValueError("视频拼接失败: clip_paths 不能为空")

    target = Path(output_path).expanduser().resolve()
    target.parent.mkdir(parents=True, exist_ok=True)
    list_file = target.parent / f"{target.stem}.concat.txt"
    lines = []
    for clip_path in clip_paths:
        source = Path(clip_path).expanduser().resolve()
        if not source.exists():
            raise FileNotFoundError(f"视频拼接失败: 片段不存在: {source}")
        escaped = str(source).replace("'", "'\\''")
        lines.append(f"file '{escaped}'")
    list_file.write_text("\n".join(lines), encoding="utf-8")

    command = [
        "ffmpeg",
        "-y",
        "-f",
        "concat",
        "-safe",
        "0",
        "-i",
        str(list_file),
        "-map",
        "0:v:0",
        "-map",
        "0:a:0?",
        "-c:v",
        "libx264",
        "-preset",
        "veryfast",
        "-crf",
        "18",
        "-pix_fmt",
        "yuv420p",
        "-c:a",
        "aac",
        "-b:a",
        "192k",
        "-fflags",
        "+genpts",
        "-avoid_negative_ts",
        "make_zero",
        "-movflags",
        "+faststart",
        str(target),
    ]
    try:
        subprocess.run(command, check=True, capture_output=True)
    except subprocess.CalledProcessError as exc:
        stderr = exc.stderr.decode(errors="ignore") if exc.stderr else ""
        raise RuntimeError(f"视频拼接失败: ffmpeg 执行失败, {stderr}") from exc
    finally:
        list_file.unlink(missing_ok=True)

    if not target.exists():
        raise RuntimeError(f"视频拼接失败: 未生成输出文件: {target}")
    return str(target)


def _load_config(config_path: str | None = None) -> dict[str, Any]:
    '''
    加载根目录下config.yaml配置文件
    '''
    path = Path(config_path).expanduser() if config_path else (REMIX_ROOT / "config.yaml")
    if not path.exists():
        raise FileNotFoundError(f"配置文件不存在: {path}")
    try:
        import yaml  # type: ignore

        data = yaml.safe_load(path.read_text(encoding="utf-8"))
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
                f"path = pathlib.Path(r'''{path}'''); "
                "print(json.dumps(yaml.safe_load(path.read_text(encoding='utf-8'))))"
            ),
        ]
        result = subprocess.run(command, check=True, capture_output=True, text=True)
        data = json.loads((result.stdout or "").strip().splitlines()[-1])
    if not isinstance(data, dict):
        raise ValueError(f"配置文件格式错误: {path}")
    return data


def _get_sales_detect_llm_config(config_path: str | None = None) -> dict[str, Any]:
    '''
    获取配置文件下llm下的配置，用于切换不同模型执行不同任务
    '''
    config = _load_config(config_path)
    llm_cfg = (config.get("llm") or {}).get("sales_detect") or {}
    required = ["base_url", "api_key", "model", "timeout"]
    missing = [key for key in required if not llm_cfg.get(key)]
    if missing:
        raise ValueError(f"llm.sales_detect 缺少必填项: {missing}")
    return {
        "base_url": str(llm_cfg["base_url"]),
        "api_key": str(llm_cfg["api_key"]),
        "model": str(llm_cfg["model"]),
        "timeout": int(llm_cfg["timeout"]),
        "temperature": float(llm_cfg.get("temperature", 0.0)),
        "top_p": float(llm_cfg.get("top_p", 1.0)),
        "max_tokens": int(llm_cfg.get("max_tokens", 8)) if llm_cfg.get("max_tokens") is not None else None,
        "enable_thinking": bool(llm_cfg.get("enable_thinking", False)),
    }


def _parse_sales_detect_result(raw_output: str) -> int:
    '''
    解析LLM返回的销售检测结果，支持多种表达方式，返回1表示销售相关，0表示非销售
    '''
    text = (raw_output or "").strip()
    if not text:
        return 0
    matched = re.search(r"[01]", text)
    if matched:
        return int(matched.group(0))

    normalized = re.sub(r"[^0-9a-zA-Z\u4e00-\u9fff]+", "", text).lower()
    if normalized in {"1", "yes", "true", "是", "销售", "sales", "sale"}:
        return 1
    if normalized in {"0", "no", "false", "否", "非销售", "nonsales", "nonsale"}:
        return 0
    return 1 if re.search(r"销售|yes|true", normalized) else 0


def _parse_sales_segment_classification(raw_output: str) -> str:
    text = (raw_output or "").strip()
    if not text:
        return "chat"
    normalized = re.sub(r"[^0-9a-zA-Z\u4e00-\u9fff]+", "", text).lower()
    if normalized in {"sales", "sale", "销售", "带货", "营销", "1"}:
        return "sales"
    if normalized in {"bridge", "过渡", "承接"}:
        return "bridge"
    if normalized in {"chat", "闲聊", "非销售", "0"}:
        return "chat"
    if re.search(r"bridge|过渡|承接", normalized):
        return "bridge"
    if re.search(r"sales|sale|销售|带货|营销", normalized):
        return "sales"
    return "chat"


def classify_sales_segments_with_llm(
    *, asr_segments: list[dict], config_path: str | None = None
) -> list[dict[str, Any]]:
    from utils.llm_client import call_llm

    llm_cfg = _get_sales_detect_llm_config(config_path)
    results: list[dict[str, Any]] = []
    for segment in asr_segments or []:
        asr_text = str(segment.get("asr_text") or segment.get("text") or "").strip()
        if not asr_text:
            continue
        prompt = (
            "你是中文直播口播分类器。请将下面这段 ASR 文本分类为三类之一：sales、chat、bridge。\n"
            "sales：明确带货、介绍商品、价格优惠、下单引导、卖点说明。\n"
            "chat：闲聊、感谢、点名互动、气氛话术、与商品无关。\n"
            "bridge：弱商品相关的过渡承接句，如“我跟你说”“这个很重要”。\n"
            "只允许输出一个标签：sales、chat、bridge。\n\n"
            f"ASR文本：\n{asr_text}"
        )
        output = call_llm(
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
        start_sec = round(float(segment.get("start_sec", 0.0)), 3)
        end_sec = round(float(segment.get("end_sec", start_sec)), 3)
        results.append(
            {
                "id": str(segment.get("id") or segment.get("segment_id") or uuid.uuid4()),
                "start_sec": start_sec,
                "end_sec": end_sec,
                "duration_sec": round(max(end_sec - start_sec, 0.0), 3),
                "asr_text": asr_text,
                "classification": _parse_sales_segment_classification(output),
            }
        )
    return results


def resolve_bridge_segments(classified_segments: list[dict[str, Any]]) -> list[dict[str, Any]]:
    resolved: list[dict[str, Any]] = []
    total = len(classified_segments)
    index = 0
    while index < total:
        segment = classified_segments[index]
        item = dict(segment)
        classification = item.get("classification") or "chat"
        if classification == "sales":
            item["keep_flag"] = True
            resolved.append(item)
            index += 1
            continue
        if classification == "chat":
            item["keep_flag"] = False
            resolved.append(item)
            index += 1
            continue

        bridge_start = index
        while index < total and (classified_segments[index].get("classification") or "chat") == "bridge":
            index += 1
        bridge_end = index
        left_class = None
        right_class = None
        for left_index in range(bridge_start - 1, -1, -1):
            candidate = classified_segments[left_index].get("classification") or "chat"
            if candidate != "bridge":
                left_class = candidate
                break
        for right_index in range(bridge_end, total):
            candidate = classified_segments[right_index].get("classification") or "chat"
            if candidate != "bridge":
                right_class = candidate
                break
        keep_flag = left_class == "sales" and right_class == "sales"
        for bridge_index in range(bridge_start, bridge_end):
            bridge_item = dict(classified_segments[bridge_index])
            bridge_item["keep_flag"] = keep_flag
            resolved.append(bridge_item)
    return resolved


def build_sales_clip_candidates(
    classified_segments: list[dict[str, Any]],
    *,
    min_duration_sec: float = 40.0,
    max_duration_sec: float = 90.0,
    pause_gap_sec: float = 5.0,
) -> list[dict[str, Any]]:
    kept_segments = [dict(item) for item in classified_segments if item.get("keep_flag")]
    candidate_groups: list[dict[str, Any]] = []
    current_segments: list[dict[str, Any]] = []
    current_duration = 0.0

    def flush_candidate():
        nonlocal current_segments, current_duration
        if not current_segments:
            return
        candidate_groups.append(
            {
                "segments": current_segments,
                "duration_sec": round(current_duration, 3),
            }
        )
        current_segments = []
        current_duration = 0.0

    for segment in kept_segments:
        gap_sec = 0.0
        if current_segments:
            previous = current_segments[-1]
            gap_sec = max(float(segment["start_sec"]) - float(previous["end_sec"]), 0.0)
        next_duration = current_duration + float(segment["duration_sec"])
        should_split_for_pause = bool(current_segments) and current_duration >= min_duration_sec and gap_sec >= pause_gap_sec
        should_split_for_max_duration = bool(current_segments) and next_duration > max_duration_sec
        if should_split_for_pause or should_split_for_max_duration:
            flush_candidate()
        current_segments.append(segment)
        current_duration += float(segment["duration_sec"])

    flush_candidate()

    if len(candidate_groups) > 1:
        current_group = candidate_groups[-1]
        while current_group["duration_sec"] < min_duration_sec and len(candidate_groups) > 1:
            previous_group = candidate_groups[-2]
            if not previous_group["segments"]:
                candidate_groups.pop(-2)
                continue
            moved_segment = previous_group["segments"].pop()
            previous_group["duration_sec"] = round(
                previous_group["duration_sec"] - float(moved_segment["duration_sec"]),
                3,
            )
            current_group["segments"].insert(0, moved_segment)
            current_group["duration_sec"] = round(
                current_group["duration_sec"] + float(moved_segment["duration_sec"]),
                3,
            )
            if not previous_group["segments"]:
                candidate_groups.pop(-2)

    candidates: list[dict[str, Any]] = []
    for clip_index, group in enumerate(candidate_groups, start=1):
        segments = group["segments"]
        candidates.append(
            {
                "clip_index": clip_index,
                "duration_sec": round(float(group["duration_sec"]), 3),
                "segment_refs": [segment["id"] for segment in segments],
                "source_time_ranges": [
                    {
                        "start_sec": segment["start_sec"],
                        "end_sec": segment["end_sec"],
                    }
                    for segment in segments
                ],
                "preview_text": " ".join(segment["asr_text"] for segment in segments).strip(),
            }
        )
    return candidates


def detect_sales_segments_from_asr(
    *, asr_segments: list[dict], config_path: str | None = None
) -> list[dict[str, Any]]:
    '''
    检测文本是否属于销售相关内容，返回包含起始时间、结束时间、持续时长和文本的列表
    '''
    from utils.llm_client import call_llm

    llm_cfg = _get_sales_detect_llm_config(config_path)
    results: list[dict[str, Any]] = []
    for segment in asr_segments or []:
        asr_text = str(segment.get("asr_text") or segment.get("text") or "").strip()
        if not asr_text:
            continue
        prompt = (
            "你是中文短视频销售话术识别器。请判断下面这段 ASR 文本是否属于销售/带货/营销转化内容。\n"
            "若包含产品推荐、价格优惠、下单引导、购买号召，返回 1；否则返回 0。\n"
            "仅允许输出单个字符：1 或 0。\n\n"
            f"ASR文本：\n{asr_text}"
        )
        output = call_llm(
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
        if _parse_sales_detect_result(output) != 1:
            continue
        start_sec = round(float(segment.get("start_sec", 0.0)), 3)
        end_sec = round(float(segment.get("end_sec", start_sec)), 3)
        results.append(
            {
                "start_sec": start_sec,
                "end_sec": end_sec,
                "duration_sec": round(max(end_sec - start_sec, 0.0), 3),
                "asr_text": asr_text,
            }
        )
    return results


def build_remix_segments(
    *,
    video_id: str,
    video_path: str,
    asr_full_text: str,
    asr_segments: list[dict],
    output_dir: str,
) -> list[dict]:
    '''
    将特定的视频片段进行切分，输出包含片段ID、起始时间、结束时间、持续时长、ASR文本和切分后视频路径的列表
    '''
    del asr_full_text
    target_dir = Path(output_dir).expanduser().resolve()
    target_dir.mkdir(parents=True, exist_ok=True)

    sales_segments = detect_sales_segments_from_asr(asr_segments=asr_segments)
    results: list[dict[str, Any]] = []
    for segment in sales_segments:
        start_sec = round(float(segment.get("start_sec", 0.0)), 3)
        end_sec = round(float(segment.get("end_sec", start_sec)), 3)
        duration_sec = round(max(end_sec - start_sec, 0.0), 3)
        asr_text = str(segment.get("asr_text") or "").strip()
        if not asr_text:
            continue

        segment_id = str(segment.get("segment_id") or uuid.uuid4())
        clip_path = target_dir / f"{segment_id}.mp4"
        cut_video_clip(
            video_path=video_path,
            start_sec=start_sec,
            end_sec=end_sec,
            output_path=str(clip_path),
        )
        results.append(
            {
                "segment_id": segment_id,
                "start_sec": start_sec,
                "end_sec": end_sec,
                "duration_sec": duration_sec,
                "asr_text": asr_text,
                "segment_file_path": str(clip_path.resolve()),
            }
        )

    return results


def rewrite_sales_text(
    *,
    segment_asr_text: str,
    product_prompt: str,
    product_doc_text: str,
    config_path: str | None = None,
) -> str:
    '''
    改写销售文案,对原有的asr文字进行改写
    '''
    from utils.llm_client import call_llm

    config = _load_config(config_path)
    llm_cfg = (config.get("llm") or {}).get("gen_word") or {} # 使用gen_word的模型配置
    required = ["base_url", "api_key", "model", "timeout"]
    missing = [key for key in required if not llm_cfg.get(key)]
    if missing:
        raise ValueError(f"文案改写失败: llm.gen_word 缺少必填项: {missing}")

    prompt = (
        "你是直播口播改写助手。请基于原始口播的语气、节奏和卖货风格，"
        "围绕商品卖点做模仿性改写。要求：\n"
        "1. 只输出最终改写文案，不要解释；\n"
        "2. 保持中文自然口语化，适合视频口播；\n"
        "3. 优先保留原文节奏和句式，但内容需贴合商品信息；\n"
        "4. 不要编造明显超出商品信息的功效。\n"
        "5. 语句通顺，逻辑清晰，能够突出商品卖点，吸引观众兴趣。\n\n"
        f"原始口播：\n{segment_asr_text}\n\n"
        f"商品提示词：\n{product_prompt}\n\n"
        f"商品文档：\n{product_doc_text or '无'}"
    )
    rewritten = call_llm(
        prompt=prompt,
        base_url=str(llm_cfg["base_url"]),
        api_key=str(llm_cfg["api_key"]),
        model=str(llm_cfg["model"]),
        timeout=int(llm_cfg["timeout"]),
        temperature=float(llm_cfg.get("temperature", 0.7)),
        top_p=float(llm_cfg.get("top_p", 0.9)),
        max_tokens=llm_cfg.get("max_tokens"),
        enable_thinking=bool(llm_cfg.get("enable_thinking", False)),
    ).strip()
    if not rewritten:
        raise RuntimeError("文案改写失败: LLM 返回空文本")
    return rewritten


def generate_script_candidates(
    *,
    base_video_path: str,
    base_video_asr_text: str,
    prompt_text: str,
    product_doc_text: str,
    count: int,
    config_path: str | None = None,
) -> list[dict]:
    '''
    根据asr中的文字内容和商品信息，生成多个候选的改写文案，用于后续选择最优文案进行视频生成
    '''
    from utils.llm_client import call_llm

    config = _load_config(config_path)
    llm_cfg = (config.get("llm") or {}).get("gen_word") or {}
    required = ["base_url", "api_key", "model", "timeout"]
    missing = [key for key in required if not llm_cfg.get(key)]
    if missing:
        raise ValueError(f"撰写改写失败: llm.gen_word 缺少必填项: {missing}")



def generate_tts_audio(
    *,
    segment_video_path: str,
    rewritten_text: str,
    temp_dir: str,
    task_item_id: str,
) -> str:
    '''
    声音克隆
    '''
    config = _load_config()
    tts_cfg = config.get("tts") or {}
    output_path = Path(temp_dir).expanduser().resolve() / f"{task_item_id}.wav"
    request_kwargs = {
        "video_path": str(Path(segment_video_path).expanduser().resolve()),
        "text": rewritten_text,
        "output_path": str(output_path),
        "ref_duration": float(tts_cfg.get("ref_duration", 5.0)),
    }
    try:
        return _get_tts_adapter().clone_from_video(**request_kwargs)
    except Exception as exc:
        raise RuntimeError(f"TTS 失败: {exc}") from exc


def generate_remix_video(
    *,
    segment_video_path: str,
    tts_audio_path: str,
    output_dir: str,
    task_item_id: str,
    aspect_mode: str,
    resolution: str,
    subtitle_enabled: bool,
) -> str:
    '''
    使用克隆后的语音和原视频生成新的混剪视频
    '''
    del task_item_id, aspect_mode, resolution, subtitle_enabled
    command = [
        "conda",
        "run",
        "-n",
        "AIGC",
        "python",
        str(REMIX_ROOT / "scripts" / "run_comfyui_video.py"),
        "--video-path",
        str(Path(segment_video_path).expanduser().resolve()),
        "--audio-path",
        str(Path(tts_audio_path).expanduser().resolve()),
        "--output-dir",
        str(Path(output_dir).expanduser().resolve()),
    ]
    try:
        result = subprocess.run(command, check=True, capture_output=True, text=True)
    except subprocess.CalledProcessError as exc:
        raise RuntimeError(f"视频生成失败: {exc.stderr or exc.stdout or exc}") from exc
    payload = json.loads((result.stdout or "").strip().splitlines()[-1])
    output_path = Path(payload["output_video_url"]).expanduser().resolve()
    if not output_path.exists():
        raise RuntimeError(f"视频生成失败: 输出文件不存在: {output_path}")
    return str(output_path)


def submit_remix_video_job(
    *,
    segment_video_path: str,
    tts_audio_path: str,
    output_dir: str,
) -> str:
    '''
    提交生成视频任务
    '''
    if _get_comfy_mode() == "service":
        payload = _get_comfy_client().post_json(
            "/jobs",
            json={
                "task_type": "remix",
                "video_path": str(Path(segment_video_path).expanduser().resolve()),
                "audio_path": str(Path(tts_audio_path).expanduser().resolve()),
                "output_dir": str(Path(output_dir).expanduser().resolve()),
            },
        )
        prompt_id = str(payload.get("prompt_id") or "").strip()
        if not prompt_id:
            raise RuntimeError(f"视频生成提交失败: 未返回 prompt_id, payload={payload}")
        return prompt_id
    command = [
        "conda",
        "run",
        "-n",
        "AIGC",
        "python",
        str(REMIX_ROOT / "scripts" / "run_comfyui_video.py"),
        "--action",
        "submit",
        "--video-path",
        str(Path(segment_video_path).expanduser().resolve()),
        "--audio-path",
        str(Path(tts_audio_path).expanduser().resolve()),
        "--output-dir",
        str(Path(output_dir).expanduser().resolve()),
    ]
    try:
        result = subprocess.run(command, check=True, capture_output=True, text=True)
    except subprocess.CalledProcessError as exc:
        raise RuntimeError(f"视频生成提交失败: {exc.stderr or exc.stdout or exc}") from exc
    payload = json.loads((result.stdout or "").strip().splitlines()[-1])
    prompt_id = str(payload.get("prompt_id") or "").strip()
    if not prompt_id:
        raise RuntimeError(f"视频生成提交失败: 未返回 prompt_id, payload={payload}")
    return prompt_id


def poll_remix_video_job(
    *,
    prompt_id: str,
    output_dir: str,
) -> dict[str, Any]:
    if _get_comfy_mode() == "service":
        return _get_comfy_client().get_json(f"/jobs/{prompt_id}")
    command = [
        "conda",
        "run",
        "-n",
        "AIGC",
        "python",
        str(REMIX_ROOT / "scripts" / "run_comfyui_video.py"),
        "--action",
        "poll",
        "--prompt-id",
        prompt_id,
        "--output-dir",
        str(Path(output_dir).expanduser().resolve()),
    ]
    try:
        result = subprocess.run(command, check=True, capture_output=True, text=True)
    except subprocess.CalledProcessError as exc:
        raise RuntimeError(f"视频生成轮询失败: {exc.stderr or exc.stdout or exc}") from exc
    return json.loads((result.stdout or "").strip().splitlines()[-1])


def generate_remix_output(
    *,
    task_id: str,
    task_item_id: str,
    segment_video_path: str,
    segment_asr_text: str,
    product_prompt: str,
    product_doc_text: str,
    aspect_mode: str,
    resolution: str,
    subtitle_enabled: bool,
    temp_dir: str,
    output_dir: str,
) -> dict:
    del task_id
    temp_path = Path(temp_dir).expanduser().resolve()
    output_path = Path(output_dir).expanduser().resolve()
    temp_path.mkdir(parents=True, exist_ok=True)
    output_path.mkdir(parents=True, exist_ok=True)

    rewritten_text = rewrite_sales_text(
        segment_asr_text=segment_asr_text,
        product_prompt=product_prompt,
        product_doc_text=product_doc_text,
    )
    tts_audio_path = generate_tts_audio(
        segment_video_path=segment_video_path,
        rewritten_text=rewritten_text,
        temp_dir=str(temp_path),
        task_item_id=task_item_id,
    )
    output_video_path = generate_remix_video(
        segment_video_path=segment_video_path,
        tts_audio_path=tts_audio_path,
        output_dir=str(output_path),
        task_item_id=task_item_id,
        aspect_mode=aspect_mode,
        resolution=resolution,
        subtitle_enabled=subtitle_enabled,
    )
    return {
        "rewritten_text": rewritten_text,
        "tts_audio_path": str(Path(tts_audio_path).resolve()),
        "output_video_url": str(Path(output_video_path).resolve()),
    }


def submit_generate_remix_output(
    *,
    task_id: str,
    task_item_id: str,
    segment_video_path: str,
    segment_asr_text: str,
    product_prompt: str,
    product_doc_text: str,
    aspect_mode: str,
    resolution: str,
    subtitle_enabled: bool,
    temp_dir: str,
    output_dir: str,
) -> dict:
    del task_id, aspect_mode, resolution, subtitle_enabled
    temp_path = Path(temp_dir).expanduser().resolve()
    output_path = Path(output_dir).expanduser().resolve()
    temp_path.mkdir(parents=True, exist_ok=True)
    output_path.mkdir(parents=True, exist_ok=True)

    rewritten_text = rewrite_sales_text(
        segment_asr_text=segment_asr_text,
        product_prompt=product_prompt,
        product_doc_text=product_doc_text,
    )
    tts_audio_path = generate_tts_audio(
        segment_video_path=segment_video_path,
        rewritten_text=rewritten_text,
        temp_dir=str(temp_path),
        task_item_id=task_item_id,
    )
    prompt_id = submit_remix_video_job(
        segment_video_path=segment_video_path,
        tts_audio_path=tts_audio_path,
        output_dir=str(output_path),
    )
    return {
        "rewritten_text": rewritten_text,
        "tts_audio_path": str(Path(tts_audio_path).resolve()),
        "prompt_id": prompt_id,
    }


def run_single_segment_smoke(*, payload_path: str) -> dict:
    payload = json.loads(Path(payload_path).read_text(encoding="utf-8"))
    return generate_remix_output(**payload)
