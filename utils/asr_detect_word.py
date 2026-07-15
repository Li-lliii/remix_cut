'''
检测视频中的中文话语（含时间戳分段）
输入视频，返回视频中所说的中文话语（含时间戳分段）
使用 VAD 语音活动检测进行自然边界切分，避免句子被强行截断。
确保安装好 ffmpeg、funasr。
'''

import io
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any, Dict, List

import numpy as np
import soundfile as sf
import yaml

PROJECT_ROOT = Path(__file__).resolve().parent.parent
print(f"[INFO] PROJECT_ROOT: {PROJECT_ROOT}")
sys.path.insert(0, str(PROJECT_ROOT))

from funasr import AutoModel
from utils.llm_client import call_llm

_asr_model = None
_vad_model = None


def _resolve_shared_asset(*parts: str) -> Path:
    local_path = PROJECT_ROOT.joinpath(*parts)
    if local_path.exists():
        return local_path

    project_root_str = str(PROJECT_ROOT)
    marker = "/.worktrees/"
    if marker in project_root_str:
        canonical_root = Path(project_root_str.split(marker, 1)[0]) / "function" / "remix_cut"
        fallback_path = canonical_root.joinpath(*parts)
        if fallback_path.exists():
            return fallback_path
    return local_path


def _load_config(config_path: Any = None) -> Dict[str, Any]:
    path = Path(config_path).expanduser() if config_path else (PROJECT_ROOT / "config.yaml")
    if not path.exists():
        raise FileNotFoundError(f"配置文件不存在: {path}")
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except Exception as e:
        raise RuntimeError(f"配置文件读取失败: {path}, error={e}") from e
    if not isinstance(data, dict):
        raise ValueError(f"配置文件格式错误（应为字典）: {path}")
    return data


def _get_sales_detect_llm_config(config_path: Any = None) -> Dict[str, Any]:
    config = _load_config(config_path)
    llm_cfg = (config.get("llm") or {}).get("sales_detect") or {}

    required = ["base_url", "api_key", "model", "timeout"]
    missing = [k for k in required if not llm_cfg.get(k)]
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
    """将模型输出解析为二分类结果：1=销售段，0=非销售段。"""
    text = (raw_output or "").strip()
    if not text:
        return 0

    m = re.search(r"[01]", text)
    if m:
        return int(m.group(0))

    normalized = re.sub(r"[^0-9a-zA-Z\u4e00-\u9fff]+", "", text).lower()
    if normalized in {"1", "yes", "true", "是", "销售", "sales", "sale"}:
        return 1
    if normalized in {"0", "no", "false", "否", "非销售", "nonsales", "nonsale"}:
        return 0

    if re.search(r"不是|非销售|no|false", normalized):
        return 0
    if re.search(r"销售|yes|true", normalized):
        return 1
    return 0


def _is_sales_segment(text: str, llm_cfg: Dict[str, Any]) -> bool:
    prompt = (
        "你是中文短视频销售话术识别器。请判断下面这段 ASR 文本是否属于“销售/带货/营销转化”内容。\n"
        "判定规则：若包含产品/服务推荐、价格优惠、下单引导、私信咨询、购买号召等，返回 1；否则返回 0。\n"
        "仅允许输出单个字符：1 或 0，不要输出其他内容。\n\n"
        f"ASR文本：\n{text}"
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
    return _parse_sales_detect_result(output) == 1


def _get_asr_model(device: str = "cuda:3") -> AutoModel:
    global _asr_model
    if _asr_model is None:
        local_model_path = str(_resolve_shared_asset("Fun_ASR", "Fun-ASR-Nano-2512"))
        print(f"[INFO] Loading ASR model: {local_model_path}  device={device}")
        try:
            _asr_model = AutoModel(
                model=local_model_path,
                trust_remote_code=True,
                remote_code=str(_resolve_shared_asset("Fun_ASR", "model.py")),
                device=device,
                disable_update=True,
            )
        except Exception as e:
            raise RuntimeError(f"ASR 模型加载失败: {e}") from e
    return _asr_model


def _get_vad_model(device: str = "cuda:3") -> AutoModel:
    global _vad_model
    if _vad_model is None:
        local_vad_path = _resolve_shared_asset("Fun_ASR", "fsmn-vad")
        if local_vad_path.exists():
            model_spec = str(local_vad_path)
            extra_kwargs: Dict[str, Any] = {"disable_update": True}
        else:
            model_spec = "fsmn-vad"
            extra_kwargs = {"model_revision": "v2.0.4"}
        print(f"[INFO] Loading VAD model: {model_spec}  device={device}")
        try:
            _vad_model = AutoModel(model=model_spec, device=device, **extra_kwargs)
        except Exception as e:
            raise RuntimeError(f"VAD 模型加载失败: {e}") from e
    return _vad_model


def _extract_audio_bytes(media_path: Path) -> bytes:
    command = ["ffmpeg", "-y"]
    hwaccel = os.environ.get("FFMPEG_HWACCEL")
    if hwaccel:
        command += ["-hwaccel", hwaccel]
        hwaccel_device = os.environ.get("FFMPEG_HWACCEL_DEVICE")
        if hwaccel_device:
            command += ["-hwaccel_device", hwaccel_device]

    command += [
        "-i", str(media_path),
        "-vn",
        "-acodec", "pcm_s16le",
        "-ar", "16000",
        "-ac", "1",
        "-f", "wav",
        "pipe:1",
    ]
    try:
        result = subprocess.run(command, check=True, capture_output=True)
    except subprocess.CalledProcessError as exc:
        stderr = exc.stderr.decode(errors="ignore") if exc.stderr else ""
        raise RuntimeError(
            f"FFmpeg 音频提取失败 (exit {exc.returncode}).\ncmd: {' '.join(command)}\n{stderr}"
        ) from exc
    if not result.stdout:
        raise RuntimeError("FFmpeg 返回了空的音频数据，请确认视频文件包含音频轨道")
    return result.stdout


def _run_vad(audio_data: np.ndarray, samplerate: int, device: str) -> List[Dict[str, float]]:
    vad_model = _get_vad_model(device)
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
        tmp_path = tmp.name
    try:
        sf.write(tmp_path, audio_data, samplerate, subtype="PCM_16")
        res = vad_model.generate(input=tmp_path)
    except Exception as e:
        raise RuntimeError(f"VAD 推理失败: {e}") from e
    finally:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass

    if not res or not isinstance(res, list) or len(res) == 0:
        raise RuntimeError("VAD 返回了空结果，无法检测语音边界")
    value = res[0].get("value", [])
    if not value:
        raise RuntimeError("VAD 未检测到任何语音片段，请确认视频中包含语音内容")
    return [{"start_ms": float(seg[0]), "end_ms": float(seg[1])} for seg in value]


def _merge_vad_segments(
    vad_segments: List[Dict[str, float]],
    min_segment_ms: float = 8000.0,
    merge_gap_ms: float = 1000.0,  # 1s
) -> List[Dict[str, float]]:
    """短段合并：仅当存在短段(<8s)且相邻静音 <=1s 时进行合并。"""
    if not vad_segments:
        return []

    segs = sorted(vad_segments, key=lambda x: x["start_ms"])
    merged: List[Dict[str, float]] = []
    cur = dict(segs[0])

    for nxt in segs[1:]:
        cur_len = cur["end_ms"] - cur["start_ms"]
        nxt_len = nxt["end_ms"] - nxt["start_ms"]
        gap = max(0.0, nxt["start_ms"] - cur["end_ms"])

        should_merge = (gap <= merge_gap_ms) and (
            (cur_len < min_segment_ms) or (nxt_len < min_segment_ms)
        )
        if should_merge:
            cur["end_ms"] = max(cur["end_ms"], nxt["end_ms"])
        else:
            merged.append(cur)
            cur = dict(nxt)

    merged.append(cur)
    return merged


def _chunk_by_nearest_silence(
    segments: List[Dict[str, float]],
    target_ms: float,
    min_segment_ms: float = 8000.0,
) -> List[Dict[str, float]]:
    """
    以 target_ms 为锚点，在“最近静音边界”切分（左右都可，最近优先）。
    不做 30s 硬切兜底。
    """
    if not segments:
        return []

    chunks: List[Dict[str, float]] = []
    n = len(segments)
    i = 0

    while i < n:
        if i == n - 1:
            chunks.append({"start_ms": segments[i]["start_ms"], "end_ms": segments[i]["end_ms"]})
            break

        start_ms = segments[i]["start_ms"]
        best_k = None
        best_dist = None
        best_dur = None

        # 候选切点：每个段的 end_ms（最后一个段之后没有“边界”可切）
        for k in range(i, n - 1):
            dur = segments[k]["end_ms"] - start_ms
            dist = abs(dur - target_ms)
            if (
                best_dist is None
                or dist < best_dist
                or (dist == best_dist and dur > (best_dur if best_dur is not None else -1))
            ):
                best_dist = dist
                best_k = k
                best_dur = dur

        if best_k is None:
            chunks.append({"start_ms": start_ms, "end_ms": segments[-1]["end_ms"]})
            break

        chunks.append({"start_ms": start_ms, "end_ms": segments[best_k]["end_ms"]})
        i = best_k + 1

    # 防止出现过短 chunk：并到前一个（尽量减少碎片）
    if len(chunks) >= 2:
        compact: List[Dict[str, float]] = [chunks[0]]
        for ch in chunks[1:]:
            dur = ch["end_ms"] - ch["start_ms"]
            if dur < min_segment_ms:
                compact[-1]["end_ms"] = ch["end_ms"]
            else:
                compact.append(ch)
        chunks = compact

    return chunks


def _asr_segment(model: AutoModel, segment: np.ndarray, samplerate: int = 16000) -> str:
    if len(segment) == 0:
        raise RuntimeError("ASR 输入音频段为空")

    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
        tmp_path = tmp.name
    try:
        sf.write(tmp_path, segment, samplerate, subtype="PCM_16")
        res = model.generate(input=tmp_path, batch_size_s=300)
    except Exception as e:
        raise RuntimeError(f"ASR 推理失败: {e}") from e
    finally:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass

    if res is None:
        raise RuntimeError("ASR 返回了 None，请检查模型与输入")

    text = ""
    if isinstance(res, list) and len(res) > 0:
        item = res[0]
        if isinstance(item, dict):
            text = item.get("text", "")
        else:
            text = str(item)
    else:
        text = str(res)

    if not text.strip():
        raise RuntimeError("ASR 返回空文本，无法视为成功")
    return text.strip()


def _split_text_for_display(text: str) -> List[str]:
    parts = re.findall(r"[^。！？!?；;]+[。！？!?；;]?", text)
    parts = [p.strip() for p in parts if p and p.strip()]
    return parts if parts else [text.strip()]


def _asr_chunks_to_display_segments(asr_chunks: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    ASR 后按标点做展示级分句，并按字符占比分配时间戳（段内线性分配）。
    """
    display_segments: List[Dict[str, Any]] = []

    for ch in asr_chunks:
        text = ch["text"].strip()
        if not text:
            continue

        start_sec = float(ch["start_sec"])
        end_sec = float(ch["end_sec"])
        duration = max(0.0, end_sec - start_sec)

        sents = _split_text_for_display(text)
        if len(sents) == 1 or duration <= 1e-6:
            display_segments.append(
                {
                    "start_sec": round(start_sec, 3),
                    "end_sec": round(end_sec, 3),
                    "text": sents[0],
                }
            )
            continue

        weights = [max(1, len(s)) for s in sents]
        total_w = float(sum(weights))
        cur = start_sec

        for i, sent in enumerate(sents):
            if i == len(sents) - 1:
                nxt = end_sec
            else:
                nxt = cur + duration * (weights[i] / total_w)

            display_segments.append(
                {
                    "start_sec": round(cur, 3),
                    "end_sec": round(nxt, 3),
                    "text": sent,
                }
            )
            cur = nxt

    return display_segments


def _count_merge_chars(text: str) -> int:
    """用于短句合并的字符计数：去除空白和常见标点。"""
    cleaned = re.sub(r"[\s，。！？!?；;、,.]", "", text)
    return len(cleaned)


def _merge_short_display_segments(
    segments: List[Dict[str, Any]],
    short_chars: int = 20,
    merge_gap_sec: float = 1.0,
) -> List[Dict[str, Any]]:
    """
    展示级合并：仅当“句子字数 < short_chars 且相邻间隔 < merge_gap_sec”时合并。
    默认规则：字数<20 且 间隔<1s。
    """
    if not segments:
        return []

    merged: List[Dict[str, Any]] = [dict(segments[0])]
    for seg in segments[1:]:
        prev = merged[-1]
        gap = float(seg["start_sec"]) - float(prev["end_sec"])
        prev_chars = _count_merge_chars(prev.get("text", ""))
        cur_chars = _count_merge_chars(seg.get("text", ""))

        should_merge = (gap < merge_gap_sec) and (
            (prev_chars < short_chars) or (cur_chars < short_chars)
        )
        if should_merge:
            prev_text = prev.get("text", "").strip()
            cur_text = seg.get("text", "").strip()
            joiner = "" if (
                not prev_text
                or prev_text.endswith(("，", "。", "！", "？", ",", ".", "!", "?", "；", ";"))
            ) else "，"
            prev["text"] = f"{prev_text}{joiner}{cur_text}".strip("，")
            prev["end_sec"] = round(float(seg["end_sec"]), 3)
        else:
            merged.append(dict(seg))

    return merged


def detect_video_word(
    video_path,
    segment_seconds: int = 30,
    device: str = "cuda:3",
) -> Dict[str, Any]:
    """
    输入:
      - video_path
      - 可选 device
      - 可选 segment_seconds

    输出:
      {
          "full_text": "完整文本",
          "segments": [
              {"start_sec": 0.0, "end_sec": 1.0, "text": "第一句文本"},
              ...
          ]
      }
    """
    video_path = Path(video_path).expanduser()
    if not video_path.exists():
        raise FileNotFoundError(f"视频文件不存在: {video_path}")

    print(f"[INFO] Extracting audio from: {video_path}")
    audio_bytes = _extract_audio_bytes(video_path) # 获取音频字节流
    try:
        audio_data, samplerate = sf.read(io.BytesIO(audio_bytes))
    except Exception as e:
        raise RuntimeError(f"音频解析失败: {e}") from e

    audio_data = audio_data.astype(np.float32)
    if audio_data.ndim != 1:
        raise RuntimeError("解析出的音频不是单声道，无法继续处理")
    total_sec = len(audio_data) / samplerate
    print(f"[INFO] Audio duration: {total_sec:.1f}s  samplerate: {samplerate}Hz")

    # 将音频进行停顿划分
    print("[INFO] Running VAD...")
    vad_segments = _run_vad(audio_data, samplerate, device)
    print(f"[INFO] Raw VAD segments: {len(vad_segments)}")

    # 1) 短段合并 + 1s 静音并段
    merged_vad = _merge_vad_segments(
        vad_segments=vad_segments,
        min_segment_ms=8000.0,
        merge_gap_ms=1000.0,  # 1s
    )
    print(f"[INFO] After short-segment merge: {len(merged_vad)}")

    # 2) 以 30s 为目标，在最近静音边界切分（无硬切兜底）
    target_ms = float(segment_seconds) * 1000.0
    asr_windows = _chunk_by_nearest_silence(
        segments=merged_vad,
        target_ms=target_ms,
        min_segment_ms=8000.0,
    )
    if not asr_windows:
        raise RuntimeError("未生成有效 ASR 分段，请检查 VAD 结果")
    print(f"[INFO] Final ASR windows: {len(asr_windows)}")

    # 3) 逐段 ASR
    asr_model = _get_asr_model(device) # 调用asr模型
    asr_chunks: List[Dict[str, Any]] = [] # 将asr识别出来的每一段trunk都放在列表里面

    for idx, seg in enumerate(asr_windows, 1):
        start_ms, end_ms = seg["start_ms"], seg["end_ms"]
        start_sample = int(start_ms / 1000.0 * samplerate)
        end_sample = int(end_ms / 1000.0 * samplerate)
        audio_slice = audio_data[start_sample:end_sample]

        if len(audio_slice) == 0:
            raise RuntimeError(f"第 {idx} 段音频切片为空，切分失败")

        print(
            f"[INFO] ASR segment {idx}/{len(asr_windows)} "
            f"[{start_ms/1000:.2f}s - {end_ms/1000:.2f}s]"
        )
        text = _asr_segment(asr_model, audio_slice, samplerate)

        asr_chunks.append(
            {
                "start_sec": round(start_ms / 1000.0, 3),
                "end_sec": round(end_ms / 1000.0, 3),
                "text": text,
            }
        )

    if not asr_chunks:
        raise RuntimeError("ASR 未产生任何有效输出段，请检查音频内容或模型配置")

    # 4) ASR 后按标点做展示级分句（带时间戳）
    segments = _asr_chunks_to_display_segments(asr_chunks)
    # 5) 展示级短句合并：字数<20 且相邻间隔<1s
    segments = _merge_short_display_segments(
        segments,
        short_chars=20,
        merge_gap_sec=1.0,
    )
    if not segments:
        raise RuntimeError("标点分句后为空，无法返回有效结构化结果")

    full_text = "".join(seg["text"] for seg in segments)
    if not full_text.strip():
        raise RuntimeError("full_text 为空，不能视为成功")

    return {
        "full_text": full_text,
        "segments": segments,  # 必为非空数组
    }


def detect_remix_segments(
    video_path,
    segment_seconds=None,
    device=None,
    config_path=None,
) -> List[Dict[str, Any]]:
    """
    先做 ASR 分段，再使用 llm.sales_detect 判断每段是否为销售段。

    Returns:
      [
        {
          "start_sec": float,
          "end_sec": float,
          "duration_sec": float,
          "asr_text": str,
        },
        ...
      ]
    """
    config = _load_config(config_path)
    asr_cfg = config.get("asr") or {}
    llm_cfg = _get_sales_detect_llm_config(config_path)

    final_segment_seconds = int(segment_seconds if segment_seconds is not None else asr_cfg.get("segment_seconds", 30))
    final_device = str(device if device is not None else asr_cfg.get("device", "cuda:3"))

    asr_result = detect_video_word(
        video_path=video_path,
        segment_seconds=final_segment_seconds,
        device=final_device,
    )
    
    # 调试用：直接从文件加载 ASR 结果，跳过前面步骤
    # with open('/zhouzhiboa/bs_media/function/remix_cut/output/asr_word/25922_1_word.json', 'r', encoding='utf-8') as f:
    #     asr_result = json.load(f)

    raw_segments = asr_result.get("segments") or []
    remix_segments: List[Dict[str, Any]] = []

    for seg in raw_segments:
        asr_text = str(seg.get("text", "")).strip()
        if not asr_text:
            continue

        if not _is_sales_segment(asr_text, llm_cfg):
            continue

        start_sec = float(seg.get("start_sec", 0.0))
        end_sec = float(seg.get("end_sec", start_sec))
        duration_sec = max(0.0, end_sec - start_sec)

        remix_segments.append(
            {
                "start_sec": round(start_sec, 3),
                "end_sec": round(end_sec, 3),
                "duration_sec": round(duration_sec, 3),
                "asr_text": asr_text,
            }
        )

    return remix_segments


def detect_sales_segments_from_asr_segments(
    *,
    asr_segments: List[Dict[str, Any]],
    config_path=None,
) -> List[Dict[str, Any]]:
    '''
    使用大模型分句检测销售话语
    '''
    llm_cfg = _get_sales_detect_llm_config(config_path)
    remix_segments: List[Dict[str, Any]] = []

    for seg in asr_segments or []:
        asr_text = str(seg.get("asr_text") or seg.get("text") or "").strip()
        if not asr_text:
            continue
        if not _is_sales_segment(asr_text, llm_cfg):
            continue

        start_sec = float(seg.get("start_sec", 0.0))
        end_sec = float(seg.get("end_sec", start_sec))
        duration_sec = max(end_sec - start_sec, 0.0)
        remix_segments.append(
            {
                "start_sec": round(start_sec, 3),
                "end_sec": round(end_sec, 3),
                "duration_sec": round(duration_sec, 3),
                "asr_text": asr_text,
            }
        )

    return remix_segments


if __name__ == "__main__":
    import json

    _video_path = PROJECT_ROOT / "metahuman_platform" / "assets" / "default_voice" / "dongbei_clone_5s.wav"
    result = detect_video_word(_video_path, segment_seconds=30, device="cuda:3")

    # seg_result = detect_remix_segments(config_path=PROJECT_ROOT / "config.yaml")

    out_dir = PROJECT_ROOT / "output" / "asr_word"
    out_dir.mkdir(parents=True, exist_ok=True)

    out_json = out_dir / "25922_1_word.json"
    out_json.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[INFO] Structured result saved to: {out_json} (segments={len(result['segments'])})")

    out_txt = out_dir / "25922_1_word.txt"
    out_txt.write_text(result["full_text"], encoding="utf-8")
    print(f"[INFO] Full text saved to: {out_txt}")
