import sys
from pathlib import Path
from typing import Any, Dict, Literal, Optional

PROJECT_ROOT = Path(__file__).resolve().parent

sys.path.insert(0, str(PROJECT_ROOT))

from utils.gen_word import generate_speech_text

with open("../output/asr_word/25410_word.txt", "r", encoding="utf-8") as f:
    asr_text = f.read()

new_text = generate_speech_text(
    asr_text,
    mode="sell",
    num_segments=5,
    min_seg_chars=None,
    max_seg_chars=None,
    target_chars=100,
    llm_base_url="http://192.168.20.25:9035/v1",
    llm_api_key="catt_2025",
    model='qwen3_5-flash',
    seed=None,
)
print(f"\n[STEP 2 DONE] 话术生成完成，共 {len(new_text)} 字。")
print(new_text)