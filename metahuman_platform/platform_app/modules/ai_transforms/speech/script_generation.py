import json
import re
import subprocess
import sys
from collections import Counter
from difflib import SequenceMatcher
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[5]
REMIX_ROOT = PROJECT_ROOT
if str(REMIX_ROOT) not in sys.path:
    sys.path.insert(0, str(REMIX_ROOT))

from utils.llm_client import call_llm


def _normalize_text(text: str) -> str:
    cleaned = re.sub(r"[\s\W_]+", "", str(text or ""), flags=re.UNICODE)
    return cleaned.strip()


def _clean_candidate_text(text: str) -> str:
    cleaned = str(text or "").strip()
    cleaned = re.sub(r"^\s*\d+[\.、)]\s*", "", cleaned)
    cleaned = re.sub(r"^\s*候选[一二三四五六七八九十\d]+[:：]\s*", "", cleaned)
    cleaned = cleaned.strip("\"'“”‘’ ")
    cleaned = re.sub(r"^(?:以下是为你生成的文案[:：]?)+", "", cleaned)
    cleaned = re.sub(r"^[^:：]*文案[:：]\s*", "", cleaned)
    return cleaned.strip("。！!?；;，, ")


def _count_effective_chars(text: str) -> int:
    return len(_normalize_text(text))


def _compute_overlap_ratio(left: str, right: str) -> float:
    left_norm = _normalize_text(left)
    right_norm = _normalize_text(right)
    if not left_norm or not right_norm:
        return 0.0
    overlap = sum((Counter(left_norm) & Counter(right_norm)).values())
    return overlap / min(len(left_norm), len(right_norm))


def _compute_longest_common_ratio(left: str, right: str) -> float:
    left_norm = _normalize_text(left)
    right_norm = _normalize_text(right)
    if not left_norm or not right_norm:
        return 0.0
    match = SequenceMatcher(None, left_norm, right_norm).find_longest_match(
        0, len(left_norm), 0, len(right_norm)
    )
    return match.size / min(len(left_norm), len(right_norm))


def _compute_repeated_phrase_ratio(text: str) -> float:
    normalized = _normalize_text(text)
    if len(normalized) < 4:
        return 0.0
    window = max(2, min(6, len(normalized) // 2))
    counts: Counter[str] = Counter(
        normalized[index : index + window]
        for index in range(0, max(len(normalized) - window + 1, 0))
    )
    if not counts:
        return 0.0
    phrase, count = counts.most_common(1)[0]
    if count <= 1:
        return 0.0
    return min((len(phrase) * count) / len(normalized), 1.0)


def _is_weak_asr(base_video_asr_text: str, target_char_count: int) -> bool:
    normalized = _normalize_text(base_video_asr_text)
    if len(normalized) < 20:
        return True
    if _compute_repeated_phrase_ratio(normalized) > 0.60:
        return True
    return len(normalized) < max(int(target_char_count * 0.25), 1)


def _get_video_duration_sec(video_path: str) -> float:
    path = Path(video_path).expanduser().resolve()
    if not path.exists():
        return 0.0
    command = [
        "ffprobe",
        "-v",
        "error",
        "-show_entries",
        "format=duration",
        "-of",
        "default=noprint_wrappers=1:nokey=1",
        str(path),
    ]
    try:
        result = subprocess.run(command, capture_output=True, text=True, check=True)
        return float((result.stdout or "").strip() or 0.0)
    except (subprocess.CalledProcessError, ValueError):
        return 0.0

#从 config.yaml 读取 LLM 配置：
def _call_generation_llm(**kwargs) -> list[str]:
    llm_cfg = _get_gen_word_llm_config()
    prompt = _build_candidates_prompt(**kwargs)
    raw_output = call_llm(
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
    return _parse_candidates_output(raw_output)


def _call_single_regeneration_llm(**kwargs) -> str:
    llm_cfg = _get_gen_word_llm_config()
    prompt = _build_regeneration_prompt(**kwargs)
    raw_output = call_llm(
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
    return _parse_single_candidate_output(raw_output)


def _is_candidate_too_similar(candidate: str, existing: list[str]) -> bool:
    for item in existing:
        if _compute_overlap_ratio(candidate, item) >= 0.70:
            return True
        if _compute_longest_common_ratio(candidate, item) >= 0.60:
            return True
    return False


def _load_config() -> dict:
    config_path = REMIX_ROOT / "config.yaml"
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


def _get_gen_word_llm_config() -> dict:
    llm_cfg = (_load_config().get("llm") or {}).get("gen_word") or {}
    required = ["base_url", "api_key", "model", "timeout"]
    missing = [key for key in required if not llm_cfg.get(key)]
    if missing:
        raise ValueError(f"候选文案生成失败: llm.gen_word 缺少必填项: {missing}")
    return {
        "base_url": str(llm_cfg["base_url"]),
        "api_key": str(llm_cfg["api_key"]),
        "model": str(llm_cfg["model"]),
        "timeout": int(llm_cfg["timeout"]),
        "temperature": float(llm_cfg.get("temperature", 0.7)),
        "top_p": float(llm_cfg.get("top_p", 0.9)),
        "max_tokens": int(llm_cfg["max_tokens"]) if llm_cfg.get("max_tokens") is not None else None,
        "enable_thinking": bool(llm_cfg.get("enable_thinking", False)),
    }


def _build_candidates_prompt(
    *,
    prompt_text: str,
    product_doc_text: str,
    base_video_asr_text: str,
    target_char_count: int,
    count: int,
) -> str:
    style_reference = base_video_asr_text.strip() if base_video_asr_text.strip() else "无有效风格参考，请以自然中文口播风格输出。"
    product_reference = product_doc_text.strip() if product_doc_text.strip() else "无商品文档，请只基于用户意图与自然口播表达生成。"
    return (
        "你是中文数字人口播文案生成助手。请生成多条不雷同、可直接用于口播的候选文案。\n"
        "必须同时遵守：\n"
        f"1. 输出 {count} 条候选文案；\n"
        f"2. 每条文案目标长度约 {target_char_count} 个字，允许上下浮动 20 字；\n"
        f"3. 语气自然口语化，避免书面腔；\n"
        f"4. 多条候选必须表达结构明显不同，不能只换几个词；\n"
        f"5. 不要编造明显超出商品信息的功效；\n"
        f"6. 语句通顺，逻辑清晰，适合口播；\n"
        "7. 只输出 JSON 数组字符串，例如 [\"文案1\", \"文案2\"]，不要解释；\n"
        "8. 原视频内容只允许参考“口语节奏、停顿、语气”，不得复用其中的商品信息、数字、赠品、库存、活动机制、促销顺序、具体句式；\n"
        "9. 不得出现与原视频高度相似的表达；\n"
        "10. 如果必须表达优惠，只能用完全不同的组织方式表达。\n\n"
        f"用户意图：\n{prompt_text.strip()}\n\n"
        f"商品文档：\n{product_reference}\n\n"
        f"原视频口播风格参考（仅用于语气，不可复用内容）：\n{style_reference}\n"
    )


def _build_regeneration_prompt(
    *,
    prompt_text: str,
    product_doc_text: str,
    base_video_asr_text: str,
    source_script_text: str,
) -> str:
    style_reference = base_video_asr_text.strip() if base_video_asr_text.strip() else "无有效风格参考，请以自然中文口播风格输出。"
    product_reference = product_doc_text.strip() if product_doc_text.strip() else "无商品文档，请只基于用户意图与自然口播表达生成。"
    return (
        "你是中文数字人口播改写助手。请基于已有文案生成一条“类似一版”新文案。\n"
        "要求：\n"
        "1. 保留原文的核心卖点与意图；\n"
        "2. 明显改变句式、组织结构和表达顺序；\n"
        "3. 不要只替换少量同义词；\n"
        "4. 只输出最终单条文案，不要解释。\n\n"
        f"用户意图：\n{prompt_text.strip()}\n\n"
        f"商品文档：\n{product_reference}\n\n"
        f"原视频口播风格参考：\n{style_reference}\n\n"
        f"源文案：\n{source_script_text.strip()}\n"
    )


def _parse_candidates_output(raw_output: str) -> list[str]:
    text = str(raw_output or "").strip()
    if not text:
        return []
    try:
        payload = json.loads(text)
        if isinstance(payload, list):
            return [str(item).strip() for item in payload if str(item).strip()]
    except json.JSONDecodeError:
        pass
    lines = [line.strip(" -\t") for line in text.splitlines() if line.strip()]
    return [line for line in lines if line]


def _parse_single_candidate_output(raw_output: str) -> str:
    items = _parse_candidates_output(raw_output)
    if items:
        return items[0]
    return str(raw_output or "").strip()

#根据基础视频、原视频 ASR、用户提示词、商品文案，生成多条不雷同、适合对口型的候选口播文案。
def build_script_candidates(
    *,
    base_video_path: str,
    base_video_asr_text: str,
    prompt_text: str,
    product_doc_text: str,
    count: int,
    duration_callback,
) -> list[dict]:
    '''
    生成候选文案列表
    '''
    target_count = min(max(int(count or 1), 1), 5)
    video_duration_sec = _get_video_duration_sec(base_video_path)
    target_char_count = int(video_duration_sec * 4) if video_duration_sec > 0 else 120 # 用于控制文案生成的数量
    existing: list[str] = []
    results: list[dict] = []
    attempts = 0

    while len(results) < target_count and attempts < 3:
        attempts += 1
        outputs = _call_generation_llm(
            prompt_text=prompt_text,
            product_doc_text=product_doc_text,
            base_video_asr_text="" if _is_weak_asr(base_video_asr_text, target_char_count) else base_video_asr_text,
            target_char_count=target_char_count,
            count=target_count - len(results),
        )
        for output in outputs:
            cleaned = _clean_candidate_text(output)
            if not cleaned or _is_candidate_too_similar(cleaned, existing):
                continue
            #估算tts的时间
            duration = duration_callback(
                base_video_duration_sec=video_duration_sec,
                base_video_asr_text=base_video_asr_text,
                script_text=cleaned,
            )
            existing.append(cleaned)
            results.append(
                {
                    "content": cleaned,
                    "char_count": len(cleaned),
                    "estimated_tts_duration_sec": duration["estimated_tts_duration_sec"],
                }
            )
            if len(results) >= target_count:
                break
    if len(results) < target_count:
        raise RuntimeError("候选文案生成失败: 未能生成足够数量的不雷同候选")
    return results


def regenerate_script(
    *,
    base_video_path: str,
    base_video_asr_text: str,
    prompt_text: str,
    product_doc_text: str,
    source_script_text: str,
    duration_callback,
) -> dict:
    video_duration_sec = _get_video_duration_sec(base_video_path)
    for _ in range(3):
        output = _call_single_regeneration_llm(
            prompt_text=prompt_text,
            product_doc_text=product_doc_text,
            base_video_asr_text=base_video_asr_text,
            source_script_text=source_script_text,
        )
        cleaned = _clean_candidate_text(output)
        if not cleaned:
            continue
        if _compute_overlap_ratio(cleaned, source_script_text) >= 0.75:
            continue
        if _compute_longest_common_ratio(cleaned, source_script_text) >= 0.65:
            continue
        duration = duration_callback(
            base_video_duration_sec=video_duration_sec,
            base_video_asr_text=base_video_asr_text,
            script_text=cleaned,
        )
        return {
            "content": cleaned,
            "char_count": len(cleaned),
            "estimated_tts_duration_sec": duration["estimated_tts_duration_sec"],
        }
    raise RuntimeError("类似一版生成失败: 未能生成足够差异化的结果")
