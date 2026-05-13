"""LLM service：纯领域函数，跟入口（CLI/HTTP/cron）解耦。

不抽象 LLMClient 协议（D19）——两家都走 OpenAI 兼容，差异只是
base_url + model id。等出现真协议不兼容的 provider（如 Anthropic）
再加抽象层，那时 30 行能搞定，现在多写就是 YAGNI。
"""
from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass

from openai import AsyncOpenAI

from xishi.config import settings

@dataclass(frozen=True)
class ModelConfig:
    provider: str    # 决定用哪把 key + 哪个 base_url
    model_id: str    # 真实下发给 API 的模型字符串

# 用户面的别名 → (provider, 真实 model id)
MODELS: dict[str, ModelConfig] = {
    "kimi":      ModelConfig("moonshot", "kimi-k2-0905-preview"),
    "kimi-long": ModelConfig("moonshot", "moonshot-v1-128k"),
    "ds":        ModelConfig("deepseek", "deepseek-chat"),
}

# 每个 provider 复用一个 client——AsyncOpenAI 内部维护 httpx 连接池,
# 每次 ask 都新建会把 TCP 握手 + TLS 成本平白叠上去
_clients: dict[str, AsyncOpenAI] = {}

def _client_for(provider: str) -> AsyncOpenAI:
    if provider in _clients:
        return _clients[provider]

    if provider == "deepseek":
        client = AsyncOpenAI(api_key=settings.deepseek_api_key, base_url=settings.deepseek_base_url)
    elif provider == "moonshot":
        client = AsyncOpenAI(api_key=settings.moonshot_api_key, base_url=settings.moonshot_base_url)
    else:
        raise ValueError(f"unknown provider: {provider}")

    _clients[provider] = client
    return client


async def ask(text: str, model: str = "ds", max_tokens: int = 256) -> str:
    """问一次 LLM，返回纯文本回复。

    边界（service 层契约）：
    - 输入：纯字符串 + 配置参数
    - 输出：纯字符串
    - 不打印、不格式化、不感知谁在调（CLI / FastAPI / cron 都行）
    """
    if model not in MODELS:
        raise ValueError(f"unknown model alias: {model!r}, available: {sorted(MODELS)}")

    cfg = MODELS[model]
    client = _client_for(cfg.provider)

    response = await client.chat.completions.create(
        model=cfg.model_id,
        max_tokens=max_tokens,
        messages=[{"role": "user", "content": text}],
    )
    return response.choices[0].message.content or ""


async def ask_stream(
    text: str, model: str = "ds", max_tokens: int = 1024
) -> AsyncIterator[str]:
    """流式问 LLM，按 chunk yield 文本片段。

    跨 provider 兼容性（D5 observe 实测）：
    - Kimi 在 finish_reason='stop' 后还会多送一个 choices=[] 的 trailing chunk
      （用来携带顶层 usage）——盲取 choices[0] 会 IndexError，必须先判空
    - Kimi 最后一个有效 chunk 的 delta.content 是 None，DS 是 ''
      用 `if delta.content:` 两者都能干净跳过
    - max_tokens 默认 1024：流式输出常用于"长回复"，沿用 ask 的 256 会被截断
    """
    if model not in MODELS:
        raise ValueError(f"unknown model alias: {model!r}, available: {sorted(MODELS)}")

    cfg = MODELS[model]
    client = _client_for(cfg.provider)

    stream = await client.chat.completions.create(
        model=cfg.model_id,
        max_tokens=max_tokens,
        stream=True,
        messages=[{"role": "user", "content": text}],
    )
    async for chunk in stream:
        if not chunk.choices:
            continue
        delta = chunk.choices[0].delta
        if delta.content:
            yield delta.content
