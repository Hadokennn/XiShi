"""LLM service：纯领域函数，跟入口（CLI/HTTP/cron）解耦。

不抽象 LLMClient 协议（D19）——两家都走 OpenAI 兼容，差异只是
base_url + model id。等出现真协议不兼容的 provider（如 Anthropic）
再加抽象层，那时 30 行能搞定，现在多写就是 YAGNI。
"""
from __future__ import annotations

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
