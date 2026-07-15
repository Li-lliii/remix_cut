"""
LLM 客户端：兼容 OpenAI Chat Completions API 格式。

支持后端（只需切换 base_url 和 api_key）：
  - Ollama     : base_url="http://host:11434/v1",   api_key="ollama"
  - vLLM       : base_url="http://host:8000/v1",    api_key="token-xxx"
  - DeepSeek   : base_url="https://api.deepseek.com/v1", api_key="sk-..."
  - 阿里云 Qwen : base_url="https://dashscope.aliyuncs.com/compatible-mode/v1", api_key="sk-..."
  - 智谱 GLM   : base_url="https://open.bigmodel.cn/api/paas/v4", api_key="..."
  - MiniMax    : base_url="https://api.minimax.chat/v1", api_key="..."
  - 其他任意兼容 OpenAI Chat API 的服务

所有后端统一走 POST /chat/completions（OpenAI Chat API）。
Ollama 旧版 /api/generate 端点已废弃，统一改用 /v1 兼容层。
若后端不支持 OpenAI 格式，可在此文件中扩展新的调用方法。
"""

import re
import time
from typing import Optional

import requests


# ── 默认值（可被调用方覆盖，也可从配置文件读取后传入）────────────────────────

DEFAULT_BASE_URL = "http://192.168.20.22:11434/v1"
DEFAULT_API_KEY  = "ollama"          # Ollama 本地服务无需真实 key，占位即可
DEFAULT_MODEL    = "qwen3:32b"
DEFAULT_TIMEOUT  = 300               # 秒，长文本生成需要较长等待


# ── 思考内容清理 ───────────────────────────────────────────────────────────────

# 检测纯文本思考块开头的正则（如 vLLM + Qwen 未关闭 thinking 时输出的英文分析）
_THINKING_HEADER_RE = re.compile(
    r"^(?:Thinking\s+Process|Analysis|Deconstruct(?:ing)?|"
    r"Let\s+me\s+(?:think|analyze|break)|I(?:'ll)?\s+(?:think|analyze)|"
    r"Step\s+\d+\s*[:\.])",
    re.IGNORECASE,
)

# 显式输出标记（模型自己标注最终结果的常见写法）
_OUTPUT_MARKER_RE = re.compile(
    r"\n\s*(?:Final\s+)?(?:Output|Draft|Answer|Text|Result)[:：]\s*\n+([\s\S]+?)"
    r"(?=\n{2,}\s*\*?(?:Critique|Note)\b|\Z)",
    re.IGNORECASE,
)

# 尾部 Critique / Note 注释
_TAIL_CRITIQUE_RE = re.compile(
    r"\n{2,}\s*\*?(?:Critique|Note)\b[^\n]*(?:\n(?!\n).*)*",
    re.IGNORECASE,
)

# 分析性段落特征（序号列表、加粗标题、Markdown 星号列表）
_ANALYSIS_PARA_RE = re.compile(
    r"^(?:\d+\.\s+\*{1,2}[A-Z]|\*{1,2}[A-Z][a-z]+\*{0,2}:|[-*]\s+\*{1,2}[A-Z])"
)


def _strip_thinking_blocks(content: str) -> str:
    """
    清理 LLM 输出中的思考/推理过程，兼容以下三种格式：

    1. <think>…</think> 标签 —— Qwen3 Think / DeepSeek-R1 等思维链模型。
    2. 纯文本英文分析块 —— vLLM + Qwen 未关闭 thinking 时的 "Thinking Process:"
       格式，先尝试找显式输出标记，再退而取最后一个非分析段落。
    3. 无思考块 —— 直接返回原文，不做任何破坏性修改。
    """
    # ── 格式 1: <think>…</think> 标签 ──────────────────────────────────────
    content = re.sub(r"<think>[\s\S]*?</think>", "", content).strip()

    # ── 格式 2: 纯文本思考块 ─────────────────────────────────────────────────
    # 只在开头 300 字符内检测，避免误伤正文里偶发的英文短语
    if _THINKING_HEADER_RE.match(content[:300]):
        # 策略 A：找显式输出标记后的内容
        m = _OUTPUT_MARKER_RE.search(content)
        if m:
            candidate = _TAIL_CRITIQUE_RE.sub("", m.group(1)).strip()
            if candidate:
                return candidate

        # 策略 B：去掉尾部 Critique/Note，从末尾找第一个非分析段落
        content = _TAIL_CRITIQUE_RE.sub("", content).strip()
        paragraphs = [p.strip() for p in re.split(r"\n{2,}", content) if p.strip()]
        for para in reversed(paragraphs):
            if not _ANALYSIS_PARA_RE.match(para):
                return para

    return content


# ── 核心调用函数 ──────────────────────────────────────────────────────────────

def call_llm(
    prompt: str,
    base_url: str = DEFAULT_BASE_URL,
    api_key: str = DEFAULT_API_KEY,
    model: str = DEFAULT_MODEL,
    timeout: int = DEFAULT_TIMEOUT,
    temperature: float = 0.85,
    top_p: float = 0.9,
    max_tokens: Optional[int] = None,
    system_prompt: Optional[str] = None,
    extra_options: Optional[dict] = None,
    enable_thinking: bool = False,
) -> str:
    """
    通过 OpenAI Chat Completions API 格式调用 LLM，返回清洗后的文字。

    Args:
        prompt:          用户消息（user role）。
        base_url:        API 根路径，结尾不含斜杠；Ollama 示例：
                         "http://192.168.20.22:11434/v1"。
        api_key:         鉴权 Bearer Token；Ollama 本地服务可填任意字符串。
        model:           模型名称，与后端一致（如 "qwen3:32b"、"deepseek-chat"）。
        timeout:         HTTP 请求超时（秒）。
        temperature:     采样温度。
        top_p:           核采样概率。
        max_tokens:      最大输出 token 数；None 时由模型自行决定。
        system_prompt:   可选系统消息；None 时不附加。
        extra_options:   附加到请求体的额外字段（如 Ollama 的 "options"）。
        enable_thinking: 是否启用模型思维链推理（默认 False）。
                         - vLLM / Qwen3：通过 chat_template_kwargs 控制；
                         - Ollama：prompt 中的 /no_think 前缀已处理，此参数忽略；
                         - 其他后端：未知字段会被静默忽略，不影响正常调用。

    Returns:
        模型返回的纯文字（已过滤所有格式的思考推理块）。

    Raises:
        requests.HTTPError:    服务端返回 4xx/5xx 时抛出。
        requests.Timeout:      请求超时时抛出。
        ValueError:            响应体格式异常时抛出。
    """
    url = f"{base_url.rstrip('/')}/chat/completions"

    messages = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    messages.append({"role": "user", "content": prompt})

    payload: dict = {
        "model": model,
        "messages": messages,
        "temperature": temperature,
        "top_p": top_p,
        "stream": False,
        # vLLM + Qwen3 系列：通过 chat_template_kwargs 控制 thinking 模式；
        # Ollama / 其他后端：不认识此字段会静默忽略，不影响正常调用。
        "chat_template_kwargs": {"enable_thinking": enable_thinking},
    }
    if max_tokens is not None:
        payload["max_tokens"] = max_tokens
    if extra_options:
        payload.update(extra_options)

    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}",
    }

    print(f"[LLM] POST {url}  model={model}  "
          f"temperature={temperature}  max_tokens={max_tokens}  "
          f"enable_thinking={enable_thinking}")

    t0 = time.time()
    resp = requests.post(url, json=payload, headers=headers, timeout=timeout)
    resp.raise_for_status()
    elapsed = time.time() - t0

    data = resp.json()
    try:
        content = data["choices"][0]["message"]["content"].strip()
    except (KeyError, IndexError) as exc:
        raise ValueError(
            f"LLM 响应格式异常，无法解析 choices[0].message.content: {data}"
        ) from exc

    # 清理所有格式的思考推理块（<think> 标签 / 纯文本分析块）
    content = _strip_thinking_blocks(content)

    usage = data.get("usage", {})
    print(f"[LLM] 完成  耗时={elapsed:.1f}s  "
          f"prompt_tokens={usage.get('prompt_tokens', '?')}  "
          f"completion_tokens={usage.get('completion_tokens', '?')}  "
          f"输出={len(content)} chars")
    return content
