from __future__ import annotations

import argparse
import sys
from pathlib import Path

# 确保可以从 tests 目录直接运行时，正常导入项目模块
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from phase3_algorithms.script_generation import _build_candidates_prompt, _get_gen_word_llm_config
from utils.llm_client import call_llm


def debug_call_generation_llm_raw(
    *,
    prompt_text: str,
    product_doc_text: str,
    base_video_asr_text: str,
    target_char_count: int,
    count: int,
) -> str:
    """
    调试用：直接返回 LLM 原始输出，不做 JSON 解析、不做清洗。
    复用项目中相同的 LLM 配置、请求地址、模型参数。
    """
    llm_cfg = _get_gen_word_llm_config()
    prompt = _build_candidates_prompt(
        prompt_text=prompt_text,
        product_doc_text=product_doc_text,
        base_video_asr_text=base_video_asr_text,
        target_char_count=target_char_count,
        count=count,
    )
    return call_llm(
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


def main() -> int:
    parser = argparse.ArgumentParser(description="调试 LLM 原始返回值")
    parser.add_argument("--prompt-text", default="请生成一段关于洗发水的口播文案")
    parser.add_argument("--product-doc-text", default="")
    parser.add_argument("--base-video-asr-text", default="上二百单啊，买一百六送一百六，再送二十粒的这个机制。闭口用壳聚糖，还有最后的两百单，你们赶紧去拍啊。我跟你说，你这个如果拍不到了，不好意思，这个一百六、一百六、二十六确认收货以后送宝宝的这个机制再也不会有了啊。这个早晚都可以使用满白天，其实你没。")
    parser.add_argument("--target-char-count", type=int, default=120)
    parser.add_argument("--count", type=int, default=3)
    args = parser.parse_args()

    try:
        raw_output = debug_call_generation_llm_raw(
            prompt_text=args.prompt_text,
            product_doc_text='',
            base_video_asr_text=args.base_video_asr_text,
            target_char_count=args.target_char_count,
            count=args.count,
        )
        print(raw_output)
        return 0
    except Exception as exc:
        print(f"调用失败: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())