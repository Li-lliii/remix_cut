# filepath: \zhouzhiboa\bs_media\.worktrees\phase2-remix-minimal-loop\function\remix_cut\metahuman_platform\tests\test_LLM_phase2.py
from __future__ import annotations

import argparse
import sys
from pathlib import Path

# 让脚本可以直接从 tests 目录运行时导入项目模块
METAHUMAN_ROOT = Path(__file__).resolve().parents[1]
if str(METAHUMAN_ROOT) not in sys.path:
    sys.path.insert(0, str(METAHUMAN_ROOT))

from phase2_algorithms.remix_pipeline import _load_config
from utils.llm_client import call_llm


def _build_rewrite_sales_prompt(
    *,
    segment_asr_text: str,
    product_prompt: str,
    product_doc_text: str,
) -> str:
    return (
        "你是直播口播改写助手。请基于原始口播的语气、节奏和卖货风格，"
        "围绕商品卖点做模仿性改写。要求：\n"
        "1. 只输出最终改写文案，不要解释；\n"
        "2. 保持中文自然口语化，适合视频口播；\n"
        "3. 优先保留原文节奏和句式，但内容需贴合商品信息；\n"
        "4. 不要编造明显超出商品信息的功效。\n\n"
        f"原始口播：\n{segment_asr_text}\n\n"
        f"商品提示词：\n{product_prompt}\n\n"
        f"商品文档：\n{product_doc_text or '无'}"
    )


def debug_call_rewrite_sales_llm_raw(
    *,
    segment_asr_text: str,
    product_prompt: str,
    product_doc_text: str,
    config_path: str | None = None,
) -> str:
    """
    调试用：直接返回 rewrite_sales_text 同款 LLM 原始输出，不做二次解析。
    """
    config = _load_config(config_path)
    llm_cfg = (config.get("llm") or {}).get("gen_word") or {}
    required = ["base_url", "api_key", "model", "timeout"]
    missing = [key for key in required if not llm_cfg.get(key)]
    if missing:
        raise ValueError(f"文案改写失败: llm.gen_word 缺少必填项: {missing}")

    prompt = _build_rewrite_sales_prompt(
        segment_asr_text=segment_asr_text,
        product_prompt=product_prompt,
        product_doc_text=product_doc_text,
    )

    return call_llm(
        prompt=prompt,
        base_url=str(llm_cfg["base_url"]),
        api_key=str(llm_cfg["api_key"]),
        model=str(llm_cfg["model"]),
        timeout=int(llm_cfg["timeout"]),
        temperature=float(llm_cfg.get("temperature", 0.7)),
        top_p=float(llm_cfg.get("top_p", 0.9)),
        max_tokens=llm_cfg.get("max_tokens"),
        enable_thinking=bool(llm_cfg.get("enable_thinking", False)),
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="调试 rewrite_sales_text 对应的 LLM 原始返回")
    parser.add_argument("--segment-asr-text", default="", help="原始口播 ASR 文本")
    parser.add_argument("--product-prompt", default="", help="商品提示词")
    parser.add_argument("--product-doc-text", default="", help="商品文档")
    parser.add_argument("--config-path", default=None, help="可选：指定 config.yaml 路径")
    parser.add_argument("--print-prompt", action="store_true", help="同时打印 prompt")
    args = parser.parse_args()

    try:
        prompt = _build_rewrite_sales_prompt(
            segment_asr_text=args.segment_asr_text,
            product_prompt=args.product_prompt,
            product_doc_text=args.product_doc_text,
        )
        if args.print_prompt:
            print("===== PROMPT START =====")
            print(prompt)
            print("===== PROMPT END =====\n")

        raw_output = debug_call_rewrite_sales_llm_raw(
            segment_asr_text=args.segment_asr_text,
            product_prompt=args.product_prompt,
            product_doc_text=args.product_doc_text,
            config_path=args.config_path,
        )
        print(raw_output)
        return 0
    except Exception as exc:
        print(f"调用失败: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())