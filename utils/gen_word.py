'''
根据asr结果生成新的说话内容

支持 "chat" 和 "sell" 两种模式：
  - chat：轻松自然、口语化、贴近日常生活
  - sell：热情洋溢、节奏紧凑、突出卖点、引导购买

每次运行从ASR文字中随机抽取不同片段作为风格参考，确保多次运行不重复。
调用 192.168.20.22:11343 上的 Ollama 大模型完成文字生成，目标输出约1分钟话语。

使用方式（命令行）:
    # 直接从视频提取ASR后生成
    python gen_word.py /path/to/video.mp4 --mode sell

    # 使用已有ASR文字文件，跳过ASR识别步骤
    python gen_word.py --asr-file output/results_qwen3.txt --mode chat
'''

import random
import re
import sys
from pathlib import Path
from typing import List, Literal, Optional

from utils.llm_client import call_llm

PROJECT_ROOT = Path(__file__).resolve().parent.parent
print(f"[INFO] PROJECT_ROOT: {PROJECT_ROOT}")
sys.path.insert(0, str(PROJECT_ROOT))

# ── 常量 ─────────────────────────────────────────────────────────────────────

# 默认 LLM 接入点，支持 Ollama/vLLM/DeepSeek/Qwen/GLM 等任意 OpenAI Chat API 兼容后端
# Ollama 示例  : "http://192.168.20.22:11434/v1"
# vLLM 示例   : "http://host:8000/v1"
# DeepSeek 示例: "https://api.deepseek.com/v1"
# 阿里云 Qwen  : "https://dashscope.aliyuncs.com/compatible-mode/v1"
DEFAULT_LLM_BASE_URL = "http://192.168.20.22:11434/v1"
DEFAULT_LLM_API_KEY  = "ollama"   # Ollama 本地无需真实 key，其他云端填对应 key
DEFAULT_MODEL        = "qwen3:32b"

# 中文正常语速约250字/分钟，1分钟目标字数
WORDS_PER_MINUTE = 250

Mode = Literal["chat", "sell"]


# ── 随机片段抽取 ──────────────────────────────────────────────────────────────

def _split_into_sentences(text: str) -> List[str]:
    '''
    将ASR文字按中文句子终止标点切分为完整句子列表。

    切分依据：句号、问号、感叹号、省略号等中英文终止标点。
    切分后保留标点符号作为句尾，过滤空串。

    Args:
        text: 待切分的文字。

    Returns:
        完整句子字符串列表。
    '''
    # 以终止标点为分隔符切分，使用 re.split 并保留分隔符到句尾
    parts = re.split(r'(?<=[。！？…!?~～\n])', text)
    sentences = []
    for part in parts:
        s = part.strip()
        if s:
            sentences.append(s)
    return sentences


def _select_random_segments(
    text: str,
    num_segments: int = 5,
    min_seg_chars: int = 20,
    max_seg_chars: int = 150,
    seed: Optional[int] = None,
) -> List[str]:
    '''
    从自动语音识别文本中随机选取一个连续的句子片段。
    “num_segments” 现在表示将用作参考背景的连续句子的数量。
    “min_seg_chars” 和 “max_seg_chars” 仅保留其原有含义以保持与之前的兼容性，但当前的筛选逻辑并不使用它们。
    '''
    if not text.strip():
        return []

    _ = min_seg_chars, max_seg_chars
    rng = random.Random(seed)
    sentences = _split_into_sentences(text)
    if not sentences:
        stripped = text.strip()
        return [stripped] if stripped else []

    window_size = max(1, num_segments)
    if len(sentences) <= window_size:
        return [''.join(sentences)]

    start = rng.randint(0, len(sentences) - window_size)
    return [''.join(sentences[start:start + window_size])]


# ── Prompt 构建 ──────────────────────────────────────────────────────────────

def _build_prompt_casual(segments: List[str], target_chars: int) -> str:
    '''
    构建"chat"模式的 LLM Prompt。
    
    chat风格特点：真实自然的口语表达，像日常聊天一样有互动感、有情绪起伏。
    Prompt 设计思路：强调内容重构而非简单模仿，保持风格但变换具体话题。
    '''
    reference = "\n---\n".join(segments)
    return (
        f"/no_think\n"
        f"你是一位正在直播的主播，正在和观众们轻松聊天。你的说话风格和内容基于以下参考片段：\n\n"
        f"【参考片段】\n{reference}\n\n"
        f"请仔细分析以上片段中的：\n"
        f"1. 说话节奏\n"
        f"2. 常用表达方式\n"
        f"3. 情绪表达特点（\n"
        f"4. 互动习惯\n"
        f"现在，请你以同样的说话风格，但**换成全新的话题内容**，生成一段直播中的聊天话术。\n\n"
        # f"内容要求：\n"
        # f"1. 话题可以是：今天发生的趣事、对某件事的感受等\n"
        # f"2. 要有真实直播的感觉：可以有适度的重复、停顿、语气词，不要过于流畅完美\n"
        # f"3. 要有互动感：可以假装看到观众评论，或者向观众提问\n"
        # f"4. 情绪要自然：有高低起伏，不是平淡的叙述\n"
        # f"5. 不要有“哈哈哈”， “笑死”等人说着会笑的字眼\n"
        f"输出要求：\n"
        f"1. 只输出说话内容，不加任何说明、标题或前缀\n"
        f"2. 字数控制在{target_chars}字左右\n"
        f"3. 让内容听起来像一个真实主播在直播间的自然聊天，而不是背诵稿子"
    )


def _build_prompt_promotion(segments: List[str], target_chars: int) -> str:
    '''
    构建"sell"模式的 LLM Prompt。
    
    sell风格特点：真实的直播带货话术，有节奏感、有情绪张力、有互动。
    Prompt 设计思路：保留参考片段的说话风格，但变换具体产品和话术内容。
    '''
    reference = "\n---\n".join(segments)
    return (
        f"/no_think\n"
        f"你是一位正在直播带货的主播，你的推销风格基于以下参考片段：\n\n"
        f"【参考片段】\n{reference}\n\n"
        f"请仔细分析以上片段中的：\n"
        f"1. 与观众互动的特点\n"
        f"2. 口头禅和个人特色表达\n\n"
        f"现在，请你以同样的说话风格和同样推销的产品内容，生成一段直播话术。\n\n"
        # f"1. 要有真实直播的感觉：语速有快慢变化，可以有适度的重复和语气词\n"
        # f"2. 要有互动：假装回应评论、催单、提醒库存等\n"
        # f"3. 情绪要真实：从介绍产品时的兴奋，到催单时的紧迫，要有层次感\n"
        # f"4. 内容要具体：不要空洞的夸赞，要有具体的描述（比如'这个面料摸起来...'）\n"
        # f"5. 包含卖点介绍、优惠信息、行动召唤，但要用自然的直播方式表达\n\n"
        f"输出要求：\n"
        f"1. 只输出说话内容，不加任何说明、标题或前缀\n"
        f"2. 字数控制在{target_chars}字左右\n"
        f"3. 让内容听起来像主播在直播间真实的即兴发挥，而不是背诵文案"
        f"4. 不要有硬推销的字眼，要让话术听起来像是主播在和观众分享好东西。"
        f"5. 生成的术语前后需要有逻辑。"
    )

# ── LLM 调用 ──────────────────────────────────────────────────────────────

def _call_llm(
    prompt: str,
    llm_base_url: str = DEFAULT_LLM_BASE_URL,
    llm_api_key: str = DEFAULT_LLM_API_KEY,
    model: str = DEFAULT_MODEL,
    timeout: int = 180,
    target_chars: int = WORDS_PER_MINUTE,
) -> str:
    '''
    调用 LLM 生成话术文字，通过统一 OpenAI Chat API 格式对接任意后端。

    支持 Ollama / vLLM / DeepSeek / 阿里云 Qwen / 智谱 GLM / MiniMax 等，
    只需修改 llm_base_url / llm_api_key 即可切换后端，无需改动业务逻辑。

    Args:
        prompt:       完整的 LLM Prompt 字符串。
        llm_base_url: LLM API 根路径（OpenAI Chat 格式）。
        llm_api_key:  鉴权 Token，Ollama 本地可填 "ollama"。
        model:        模型名称。
        timeout:      HTTP 请求超时（秒）。
        target_chars: 期望输出的目标字符数（用于估算 max_tokens）。

    Returns:
        模型生成的文字（已去除 <think>…</think> 推理块）。
    '''
    # 输出 token 按目标字数的 3 倍给足空间（含标点、空格）
    max_tokens = max(512, target_chars * 3)
    return call_llm(
        prompt=prompt,
        base_url=llm_base_url,
        api_key=llm_api_key,
        model=model,
        timeout=timeout,
        temperature=0.85,
        top_p=0.9,
        max_tokens=max_tokens,
    )


# ── 主函数 ───────────────────────────────────────────────────────────────────

def generate_speech_text(
    asr_text: str,
    mode: Mode = "chat",
    num_segments: int = 5,
    min_seg_chars: int = 20,
    max_seg_chars: int = 150,
    target_chars: int = WORDS_PER_MINUTE,
    llm_base_url: str = DEFAULT_LLM_BASE_URL,
    llm_api_key: str = DEFAULT_LLM_API_KEY,
    model: str = DEFAULT_MODEL,
    timeout: int = 180,
    seed: Optional[int] = None,
) -> str:
    '''
    Generate new speech text from ASR content using one contiguous sentence window.

    支持通过 llm_base_url / llm_api_key 指定任意 OpenAI Chat API 兼容的 LLM 后端
    （Ollama / vLLM / DeepSeek / 阿里云 Qwen / 智谱 GLM / MiniMax 等）。

    `num_segments` means the number of consecutive sentences used as the
    reference window. `min_seg_chars` and `max_seg_chars` are kept only for
    backward compatibility and are not used by the current selection logic.
    '''
    import requests as _requests  # 仅用于异常类型判断

    if mode not in ("chat", "sell"):
        raise ValueError(f"mode must be 'chat' or 'sell', got: {mode!r}")

    print(
        f"[INFO] Mode={mode} num_segments={num_segments} "
        f"min_seg_chars={min_seg_chars} max_seg_chars={max_seg_chars} "
        f"target_chars={target_chars}"
    )
    print(f"[INFO] ASR text total length: {len(asr_text)} chars")

    # Step 1: select one contiguous sentence window as reference.
    segments = _select_random_segments(
        asr_text,
        num_segments=num_segments,
        min_seg_chars=min_seg_chars,
        max_seg_chars=max_seg_chars,
        seed=seed,
    )
    sentence_count = len(_split_into_sentences(segments[0])) if segments else 0
    print(f"[INFO] Selected 1 contiguous reference segment with {sentence_count} sentences:")
    for idx, seg in enumerate(segments, 1):
        preview = seg[:60].replace("\n", " ")
        ellipsis = "..." if len(seg) > 60 else ""
        print(f"  [{idx}] {preview}{ellipsis}")

    print('完整的选取参考片段内容：\n')
    print(segments)

    # Step 2: build the prompt.
    if mode == "chat":
        prompt = _build_prompt_casual(segments, target_chars)
    else:
        prompt = _build_prompt_promotion(segments, target_chars)

    # Step 3: generate text with LLM.
    try:
        generated = _call_llm(
            prompt,
            llm_base_url=llm_base_url,
            llm_api_key=llm_api_key,
            model=model,
            timeout=timeout,
            target_chars=target_chars,
        )
    except _requests.RequestException as exc:
        raise RuntimeError(f"LLM request failed: {exc}") from exc

    print(f"[INFO] Generation complete. Output length: {len(generated)} chars")
    return generated


# ── 入口 ─────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description="根据视频ASR内容生成指定风格话语（chat / sell）",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "video", nargs="?",
        help="输入视频路径（不传且未指定 --asr-file 时使用默认测试视频）",
    )
    parser.add_argument(
        "--asr-file", metavar="PATH",
        help="已有ASR文字文件路径（.txt），若提供则跳过视频ASR识别步骤直接读取",
    )
    parser.add_argument(
        "--mode", choices=["chat", "sell"], default="chat",
        help="生成模式",
    )
    parser.add_argument(
        "--segments", type=int, default=5,
        help="number of consecutive sentences used as the reference window",
    )
    parser.add_argument(
        "--min-seg-chars", type=int, default=20,
        help="deprecated compatibility option; unused by contiguous sentence selection",
    )
    parser.add_argument(
        "--max-seg-chars", type=int, default=150,
        help="deprecated compatibility option; unused by contiguous sentence selection",
    )
    parser.add_argument(
        "--target-chars", type=int, default=WORDS_PER_MINUTE,
        help="生成话语的目标字符数（约1分钟=250字）",
    )
    parser.add_argument(
        "--model", default=DEFAULT_MODEL,
        help="Ollama 模型名称",
    )
    parser.add_argument(
        "--device", default="cuda:3",
        help="ASR推理设备（仅在需要运行ASR识别时有效）",
    )
    args = parser.parse_args()

    # ── 获取 ASR 文字 ────────────────────────────────────────────────────
    if args.asr_file:
        asr_path = Path(args.asr_file)
        if not asr_path.exists():
            print(f"[ERROR] ASR 文件不存在: {asr_path}", file=sys.stderr)
            sys.exit(1)
        asr_text = asr_path.read_text(encoding="utf-8")
        print(f"[INFO] 从文件加载ASR文字: {asr_path} ({len(asr_text)} chars)")
    else:
        from utils.asr_detect_word import detect_video_word
        video_path = Path(args.video) if args.video else PROJECT_ROOT / "video_720" / "2618_gpu.mp4"
        asr_text = detect_video_word(video_path, segment_seconds=30, device=args.device)

    # ── 生成话语 ─────────────────────────────────────────────────────────
    result = generate_speech_text(
        asr_text,
        mode=args.mode,
        num_segments=args.segments,
        min_seg_chars=args.min_seg_chars,
        max_seg_chars=args.max_seg_chars,
        target_chars=args.target_chars,
        model=args.model,
    )

    sep = "=" * 60
    print(f"\n{sep}\n[MODE: {args.mode}] 生成结果：\n{sep}")
    print(result)
    print(f"{sep}\n")

    # ── 保存结果 ─────────────────────────────────────────────────────────
    out_file = PROJECT_ROOT / "output" / f"gen_word_{args.mode}.txt"
    out_file.parent.mkdir(parents=True, exist_ok=True)
    out_file.write_text(result, encoding="utf-8")
    print(f"[INFO] 结果已保存至: {out_file}")
