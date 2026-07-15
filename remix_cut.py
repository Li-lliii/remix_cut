import sys
from pathlib import Path
from typing import Any, Dict, Literal, Optional

PROJECT_ROOT = Path(__file__).resolve().parent

sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT / "Qwen3-TTS"))  # 使 qwen_tts 包可被导入


# ── 配置文件加载 ──────────────────────────────────────────────────────────────

def load_config(config_path: Optional[str] = None) -> Dict[str, Any]:
    """
    加载 YAML 配置文件，返回配置字典。

    Args:
        config_path: 配置文件路径；None 时自动寻找项目根目录下的 config.yaml。

    Returns:
        配置字典；文件不存在时返回空字典（使用各函数内置默认值）。
    """
    import yaml  # 懒加载，避免无 yaml 时整个模块无法导入

    path = Path(config_path) if config_path else PROJECT_ROOT / "config.yaml"
    if not path.exists():
        print(f"[WARN] 配置文件不存在: {path}，使用内置默认值。")
        return {}
    with open(path, encoding="utf-8") as f:
        cfg = yaml.safe_load(f) or {}
    print(f"[INFO] 已加载配置文件: {path}")
    return cfg


def _get(cfg: dict, *keys, default=None):
    """从嵌套字典中安全取值，任意层级缺失时返回 default。"""
    node = cfg
    for k in keys:
        if not isinstance(node, dict) or k not in node:
            return default
        node = node[k]
    return node if node is not None else default


# ── 主函数 ────────────────────────────────────────────────────────────────────

def generate_cloned_audio(
    video_path,
    mode: Optional[Literal["chat", "sell"]] = None,
    output_path=None,
    asr_segment_seconds: Optional[int] = None,
    asr_device: Optional[str] = None,
    tts_device: Optional[str] = None,
    gen_num_segments: Optional[int] = None,
    gen_min_seg_chars: int = 20,
    gen_max_seg_chars: int = 150,
    gen_target_chars: Optional[int] = None,
    gen_model: Optional[str] = None,
    gen_llm_base_url: Optional[str] = None,
    gen_llm_api_key: Optional[str] = None,
    asr_llm_base_url: Optional[str] = None,
    asr_llm_api_key: Optional[str] = None,
    asr_llm_model: Optional[str] = None,
    ref_duration: Optional[float] = None,
    seed: Optional[int] = None,
    config_path: Optional[str] = None,
) -> Path:
    '''
    传入一段原视频，完成以下三步并返回克隆音色的新音频文件：

      Step 1  ASR识别：调用 asr_detect_word.detect_video_word()
              提取视频中的中文语音内容，并经LLM润色得到规整文字。

      Step 2  话术生成：调用 gen_word.generate_speech_text()
              以ASR文字为风格参考，使用大模型生成指定模式（chat/sell）的新话语。

      Step 3  TTS合成：调用 tts_gen_sound.tts_from_video()
              从原视频随机截取参考音频，用 Qwen3-TTS 克隆说话人音色，
              将新话语合成为与原声音色一致的WAV音频文件。

    参数优先级：函数参数（非 None）> config.yaml > 内置默认值。

    Args:
        video_path:          原视频文件路径（str 或 Path）。
        mode:                话术生成模式，"chat"（日常聊天）或 "sell"（直播带货）。
        output_path:         输出WAV路径；None 时默认保存至 output/<视频名>_tts.wav。
        asr_segment_seconds: ASR识别时每段音频的最大时长（秒）。
        asr_device:          ASR推理设备。
        tts_device:          Qwen3-TTS推理设备，None 表示自动选择。
        gen_num_segments:    参考片段中连续句子数量。
        gen_min_seg_chars:   最小选取字符数（兼容旧接口，当前逻辑未使用）。
        gen_max_seg_chars:   最大选取字符数（兼容旧接口，当前逻辑未使用）。
        gen_target_chars:    生成话语的目标字符数（约1分钟=250字）。
        gen_model:           话术生成使用的 LLM 模型名称。
        gen_llm_base_url:    话术生成 LLM API 根路径（OpenAI Chat 格式）。
        gen_llm_api_key:     话术生成 LLM API Key。
        asr_llm_base_url:    ASR润色 LLM API 根路径。
        asr_llm_api_key:     ASR润色 LLM API Key。
        asr_llm_model:       ASR润色 LLM 模型名称。
        ref_duration:        TTS参考音频时长（秒）。
        seed:                随机种子，None 表示每次真随机，传入固定值可复现结果。
        config_path:         配置文件路径；None 时自动加载项目根目录 config.yaml。

    Returns:
        生成的语音WAV文件路径（Path对象）。

    Raises:
        FileNotFoundError: 视频文件不存在时抛出。
        RuntimeError:      任意步骤执行失败时抛出。

    Example:
        >>> result = generate_cloned_audio("video_720/2618_gpu.mp4", mode="sell")
        >>> print(f"音频已保存至: {result}")
    '''
    # ── 加载配置文件，函数参数（非 None）优先级高于配置文件 ──────────────
    cfg = load_config(config_path)

    mode                = mode                or _get(cfg, "gen_word",  "mode",            default="chat")
    asr_segment_seconds = asr_segment_seconds or _get(cfg, "asr",      "segment_seconds",  default=60)
    asr_device          = asr_device          or _get(cfg, "asr",      "device",           default="cuda:3")
    tts_device          = tts_device          or _get(cfg, "tts",      "device",           default="cuda:3")
    gen_num_segments    = gen_num_segments    or _get(cfg, "gen_word",  "num_segments",     default=5)
    gen_target_chars    = gen_target_chars    or _get(cfg, "gen_word",  "target_chars",     default=250)
    gen_model           = gen_model           or _get(cfg, "llm", "gen_word",  "model",     default="qwen3:32b")
    gen_llm_base_url    = gen_llm_base_url    or _get(cfg, "llm", "gen_word",  "base_url",  default="http://192.168.20.22:11434/v1")
    gen_llm_api_key     = gen_llm_api_key     or _get(cfg, "llm", "gen_word",  "api_key",   default="ollama")
    asr_llm_base_url    = asr_llm_base_url    or _get(cfg, "llm", "asr_polish","base_url",  default="http://192.168.20.22:11434/v1")
    asr_llm_api_key     = asr_llm_api_key     or _get(cfg, "llm", "asr_polish","api_key",   default="ollama")
    asr_llm_model       = asr_llm_model       or _get(cfg, "llm", "asr_polish","model",     default="qwen3:1.7b")
    ref_duration        = ref_duration        or _get(cfg, "tts",      "ref_duration",      default=5.0)
    if seed is None:
        seed = _get(cfg, "run", "seed", default=None)

    video_path = Path(video_path).expanduser().resolve()
    if not video_path.exists():
        raise FileNotFoundError(f"视频文件不存在: {video_path}")

    sep = "=" * 60

    # ── Step 1: ASR 识别原视频中文内容 ──────────────────────────────────
    print(f"\n{sep}")
    print(f"[STEP 1] ASR 识别视频语音内容: {video_path}")
    print(sep)
    from utils.asr_detect_word import detect_video_word
    asr_text = detect_video_word(
        video_path,
        segment_seconds=asr_segment_seconds,
        device=asr_device,
        llm_base_url=asr_llm_base_url,
        llm_api_key=asr_llm_api_key,
        llm_model=asr_llm_model,
    )
    print(f"\n[STEP 1 DONE] ASR识别完成，共 {len(asr_text)} 字。")

    # ── Step 2: 生成新话术 ───────────────────────────────────────────────
    print(f"\n{sep}")
    print(f"[STEP 2] 生成 [{mode}] 模式新话术（目标约 {gen_target_chars} 字）")
    print(sep)
    from utils.gen_word import generate_speech_text
    new_text = generate_speech_text(
        asr_text,
        mode=mode,
        num_segments=gen_num_segments,
        min_seg_chars=gen_min_seg_chars,
        max_seg_chars=gen_max_seg_chars,
        target_chars=gen_target_chars,
        llm_base_url=gen_llm_base_url,
        llm_api_key=gen_llm_api_key,
        model=gen_model,
        seed=seed,
    )
    print(f"\n[STEP 2 DONE] 话术生成完成，共 {len(new_text)} 字。")
    print(f"  内容预览: {new_text[:80].replace(chr(10), ' ')}{'...' if len(new_text) > 80 else ''}")

    # ── Step 3: TTS 克隆音色，合成新音频 ────────────────────────────────
    print(f"\n{sep}")
    print(f"[STEP 3] TTS 音色克隆 & 语音合成")
    print(sep)
    from utils.tts_gen_sound import tts_from_video
    result_path = tts_from_video(
        video_path=video_path,
        new_text=new_text,
        output_path=Path(output_path) if output_path else None,
        ref_duration=ref_duration,
        asr_device=asr_device,
        tts_device=tts_device,
        seed=seed,
    )

    print(f"\n{sep}")
    print(f"[ALL DONE] 克隆音频已生成: {result_path}")
    print(sep)
    return result_path


# ── 直接运行入口 ─────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description="视频ASR → 话术生成 → TTS音色克隆，一键生成新音频",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("video", nargs="?",
                        help="原视频路径（省略时读取 config.yaml 中的 run.default_video）")
    parser.add_argument("--config", metavar="PATH", default=None,
                        help="配置文件路径（默认: 项目根目录下 config.yaml）")
    parser.add_argument("--mode", choices=["chat", "sell"], default=None,
                        help="话术生成模式（覆盖配置文件 gen_word.mode）")
    parser.add_argument("--output", metavar="PATH", default=None,
                        help="输出WAV路径（默认: output/<视频名>_tts.wav）")
    parser.add_argument("--asr-device", default=None,
                        help="ASR推理设备（覆盖配置文件 asr.device）")
    parser.add_argument("--tts-device", default=None,
                        help="TTS推理设备（覆盖配置文件 tts.device）")
    parser.add_argument("--target-chars", type=int, default=None,
                        help="生成话语的目标字符数（覆盖配置文件 gen_word.target_chars）")
    parser.add_argument("--model", default=None,
                        help="话术生成 LLM 模型名称（覆盖配置文件 llm.gen_word.model）")
    parser.add_argument("--llm-base-url", default=None, metavar="URL",
                        help="话术生成 LLM API 根路径（覆盖配置文件 llm.gen_word.base_url）")
    parser.add_argument("--llm-api-key", default=None, metavar="KEY",
                        help="话术生成 LLM API Key（覆盖配置文件 llm.gen_word.api_key）")
    args = parser.parse_args()

    # 先加载配置，确定默认视频路径
    cfg = load_config(args.config)
    default_video = _get(cfg, "run", "default_video", default="video_720/2618_gpu.mp4")
    video = args.video or str(PROJECT_ROOT / default_video)

    result = generate_cloned_audio(
        video_path=video,
        mode=args.mode,
        output_path=args.output,
        asr_device=args.asr_device,
        tts_device=args.tts_device,
        gen_target_chars=args.target_chars,
        gen_model=args.model,
        gen_llm_base_url=args.llm_base_url,
        gen_llm_api_key=args.llm_api_key,
        config_path=args.config,
    )
    print(f"\n[INFO] 完成！输出文件: {result}")
