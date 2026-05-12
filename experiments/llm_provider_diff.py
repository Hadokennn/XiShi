"""
学习脚本：让五家 LLM API 的 raw response 摊在屏幕上对比。

跑法：
    uv run python experiments/llm_provider_diff.py            # 全 mock，无 key 可跑
    uv run python experiments/llm_provider_diff.py --real deepseek,kimi  # 这俩真实调用

固定场景：用户问"北京今天天气如何？"，所有家都给同一个 tool（get_weather），
让模型决定调它。然后我们看每家返回长什么样。
"""
from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict, dataclass, field
from typing import Any, Literal

# 不强依赖项目 settings——这个脚本要能 standalone 跑
import os
from pathlib import Path


# ============================================================
# 0. 共同的场景定义
# ============================================================

USER_PROMPT = "北京今天天气怎么样？"

TOOL_SCHEMA_ANTHROPIC = {
    "name": "get_weather",
    "description": "查询某个城市当前天气",
    "input_schema": {
        "type": "object",
        "properties": {"city": {"type": "string"}},
        "required": ["city"],
    },
}

TOOL_SCHEMA_OPENAI = {
    "type": "function",
    "function": {
        "name": "get_weather",
        "description": "查询某个城市当前天气",
        "parameters": {
            "type": "object",
            "properties": {"city": {"type": "string"}},
            "required": ["city"],
        },
    },
}


# ============================================================
# 1. Mock 数据：基于各家官方文档的真实 wire 格式
# ============================================================

MOCK_ANTHROPIC = {
    "id": "msg_01ABCxyz",
    "type": "message",
    "role": "assistant",
    "model": "claude-haiku-4-5",
    "content": [
        {"type": "text", "text": "我帮你查询北京的天气。"},
        {
            "type": "tool_use",
            "id": "toolu_01XYZ",
            "name": "get_weather",
            "input": {"city": "Beijing"},
        },
    ],
    "stop_reason": "tool_use",
    "stop_sequence": None,
    "usage": {
        "input_tokens": 423,
        "cache_creation_input_tokens": 0,
        "cache_read_input_tokens": 0,
        "output_tokens": 47,
    },
}

MOCK_OPENAI = {
    "id": "chatcmpl-9abc",
    "object": "chat.completion",
    "created": 1746789012,
    "model": "gpt-4.1",
    "choices": [
        {
            "index": 0,
            "message": {
                "role": "assistant",
                "content": None,
                "tool_calls": [
                    {
                        "id": "call_abc123",
                        "type": "function",
                        "function": {
                            "name": "get_weather",
                            "arguments": '{"city":"Beijing"}',
                        },
                    }
                ],
            },
            "finish_reason": "tool_calls",
        }
    ],
    "usage": {
        "prompt_tokens": 50,
        "completion_tokens": 18,
        "total_tokens": 68,
    },
}

MOCK_QWEN = {
    "id": "chatcmpl-qwen-xyz",
    "object": "chat.completion",
    "created": 1746789100,
    "model": "qwen-max",
    "choices": [
        {
            "index": 0,
            "message": {
                "role": "assistant",
                "content": "",
                # 千问 OpenAI 兼容模式开启 thinking 时会多这个字段
                "reasoning_content": "用户在问北京天气，调 get_weather 工具即可",
                "tool_calls": [
                    {
                        "id": "call_qwen_001",
                        "type": "function",
                        "function": {
                            "name": "get_weather",
                            "arguments": '{"city": "北京"}',
                        },
                    }
                ],
            },
            "finish_reason": "tool_calls",
        }
    ],
    "usage": {
        "prompt_tokens": 62,
        "completion_tokens": 24,
        "total_tokens": 86,
    },
}


# ============================================================
# 2. 真实调用：DeepSeek / Kimi（OpenAI 兼容协议，用 openai SDK + base_url 切换）
# ============================================================

def _load_env() -> None:
    """简单 .env 加载器，不引入 python-dotenv。"""
    env_path = Path(__file__).resolve().parent.parent / ".env"
    if not env_path.exists():
        return
    for line in env_path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip())


def call_real(provider: Literal["deepseek", "kimi"]) -> dict[str, Any]:
    """走 OpenAI SDK，base_url 切到对应厂商。返回 raw dict。"""
    from openai import OpenAI

    cfg = {
        "deepseek": {
            "key_env": "DEEPSEEK_API_KEY",
            "base_url": "https://api.deepseek.com",
            "model": "deepseek-chat",
        },
        "kimi": {
            "key_env": "MOONSHOT_API_KEY",
            "base_url": "https://api.moonshot.cn/v1",
            "model": "moonshot-v1-8k",
        },
    }[provider]

    api_key = os.environ.get(cfg["key_env"])
    if not api_key:
        raise RuntimeError(f"{cfg['key_env']} 没设置，跳过 {provider}")

    client = OpenAI(api_key=api_key, base_url=cfg["base_url"])
    resp = client.chat.completions.create(
        model=cfg["model"],
        messages=[{"role": "user", "content": USER_PROMPT}],
        tools=[TOOL_SCHEMA_OPENAI],
        tool_choice="auto",
    )
    # 转 dict 让我们能看到完整 wire 形状
    return resp.model_dump()


# ============================================================
# 3. 归一化层：模仿 Vercel AI SDK 风格的统一抽象
# ============================================================

@dataclass
class UnifiedToolCall:
    name: str
    args: dict[str, Any]
    raw_id: str  # 各家 id 命名不同（toolu_xxx / call_xxx），归一化保留以便回写


@dataclass
class UnifiedUsage:
    prompt_tokens: int
    completion_tokens: int


@dataclass
class UnifiedResponse:
    text: str | None
    tool_calls: list[UnifiedToolCall]
    finish_reason: Literal["stop", "tool_calls", "length"]
    usage: UnifiedUsage
    # 故意不暴露的字段（在最后一段会列出来——这正是 SDK 抽象的代价）


def normalize_anthropic(raw: dict) -> UnifiedResponse:
    text_parts = []
    tool_calls = []
    for block in raw["content"]:
        if block["type"] == "text":
            text_parts.append(block["text"])
        elif block["type"] == "tool_use":
            tool_calls.append(
                UnifiedToolCall(
                    name=block["name"],
                    args=block["input"],
                    raw_id=block["id"],
                )
            )
    finish_map = {"end_turn": "stop", "tool_use": "tool_calls", "max_tokens": "length"}
    return UnifiedResponse(
        text="".join(text_parts) or None,
        tool_calls=tool_calls,
        finish_reason=finish_map.get(raw["stop_reason"], "stop"),
        usage=UnifiedUsage(
            prompt_tokens=raw["usage"]["input_tokens"],
            completion_tokens=raw["usage"]["output_tokens"],
        ),
    )


def normalize_openai_compat(raw: dict) -> UnifiedResponse:
    """OpenAI / DeepSeek / Kimi / 千问（兼容模式）共用。"""
    msg = raw["choices"][0]["message"]
    tool_calls = []
    for tc in msg.get("tool_calls") or []:
        tool_calls.append(
            UnifiedToolCall(
                name=tc["function"]["name"],
                args=json.loads(tc["function"]["arguments"]),
                raw_id=tc["id"],
            )
        )
    return UnifiedResponse(
        text=msg.get("content") or None,
        tool_calls=tool_calls,
        finish_reason=raw["choices"][0]["finish_reason"],
        usage=UnifiedUsage(
            prompt_tokens=raw["usage"]["prompt_tokens"],
            completion_tokens=raw["usage"]["completion_tokens"],
        ),
    )


# ============================================================
# 4. 输出
# ============================================================

def section(title: str) -> None:
    print(f"\n{'=' * 70}\n{title}\n{'=' * 70}")


def show_raw(name: str, raw: dict) -> None:
    print(f"\n--- [{name}] raw response ---")
    print(json.dumps(raw, indent=2, ensure_ascii=False))


def show_unified(name: str, u: UnifiedResponse) -> None:
    print(f"\n--- [{name}] 归一化后（Vercel AI SDK 风格）---")
    print(json.dumps(asdict(u), indent=2, ensure_ascii=False))


LOST_FIELDS = """
[Anthropic 丢失]
  - usage.cache_creation_input_tokens / cache_read_input_tokens
    → prompt caching 命中率没法测，W6 关键指标消失
  - content 数组里 text 和 tool_use 的"穿插顺序"
    → 模型先解释再调工具 vs 先调工具再解释，归一化后看不出差别
  - extended thinking block（如果开启）会被合并进 text，无法单独 trace

[OpenAI 丢失]
  - logprobs / top_logprobs
  - reasoning_effort（o 系列）的 reasoning tokens 计数

[DeepSeek 丢失]
  - usage.prompt_cache_hit_tokens / prompt_cache_miss_tokens
    → DeepSeek 自动 caching 的命中情况看不见

[千问丢失]
  - message.reasoning_content（思考链文本）
  - DashScope 原生格式的 finish_reason 细分

[Kimi 丢失]
  - 上下文缓存的 cache_id（手动 cache 模式）

[共同丢失]
  - 各家 stop_reason / finish_reason 的"原始字符串" → 归一化后值域被压缩到 3 个
  - 各家 model 字段的具体版本号（用于排查"模型悄悄被替换"）
"""


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--real",
        default="",
        help="逗号分隔的真实调用列表，可选: deepseek,kimi（其他家保持 mock）",
    )
    args = parser.parse_args()
    real_set = {x.strip() for x in args.real.split(",") if x.strip()}

    if real_set:
        _load_env()

    # 收集每家的 raw 数据
    providers: dict[str, dict] = {
        "Anthropic (mock)": MOCK_ANTHROPIC,
        "OpenAI (mock)": MOCK_OPENAI,
        "千问 Qwen (mock)": MOCK_QWEN,
    }

    if "deepseek" in real_set:
        try:
            providers["DeepSeek (REAL)"] = call_real("deepseek")
        except Exception as e:
            print(f"⚠️  DeepSeek 真实调用失败，回退 mock: {e}", file=sys.stderr)
            providers["DeepSeek (mock)"] = {
                **MOCK_OPENAI,
                "model": "deepseek-chat",
                "usage": {**MOCK_OPENAI["usage"], "prompt_cache_hit_tokens": 0, "prompt_cache_miss_tokens": 50},
            }
    else:
        providers["DeepSeek (mock)"] = {
            **MOCK_OPENAI,
            "model": "deepseek-chat",
            "usage": {**MOCK_OPENAI["usage"], "prompt_cache_hit_tokens": 0, "prompt_cache_miss_tokens": 50},
        }

    if "kimi" in real_set:
        try:
            providers["Kimi (REAL)"] = call_real("kimi")
        except Exception as e:
            print(f"⚠️  Kimi 真实调用失败，回退 mock: {e}", file=sys.stderr)
            providers["Kimi (mock)"] = {**MOCK_OPENAI, "model": "moonshot-v1-8k"}
    else:
        providers["Kimi (mock)"] = {**MOCK_OPENAI, "model": "moonshot-v1-8k"}

    # === 段 1：raw 对比 ===
    section("段 1：五家 raw response —— 协议根的差异在这里")
    for name, raw in providers.items():
        show_raw(name, raw)

    # === 段 2：归一化后 ===
    section("段 2：归一化后（模仿 Vercel AI SDK 风格）—— 看起来都一样了")
    for name, raw in providers.items():
        if name.startswith("Anthropic"):
            show_unified(name, normalize_anthropic(raw))
        else:
            show_unified(name, normalize_openai_compat(raw))

    # === 段 3：归一化丢了什么 ===
    section("段 3：抹平的代价 —— 这些字段被 SDK 吞掉了")
    print(LOST_FIELDS)


if __name__ == "__main__":
    main()
