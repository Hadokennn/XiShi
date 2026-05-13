"""
D4 学习脚本：观察 Kimi / DeepSeek 在 `response_format=json_object` 模式下的真实输出。

跑法：
    uv run python experiments/observe_json_mode.py              # mock 模式（无 key 也能跑）
    uv run python experiments/observe_json_mode.py --real kimi  # 真实调 Kimi
    uv run python experiments/observe_json_mode.py --real kimi,ds  # 两家都真实跑

目的（observe-before-implement）：
    - 验证 json_object 模式下，模型是否真的稳定吐合法 JSON
    - 看是否会塞 ```json ... ``` fence
    - 看 schema 字段稳定性：会不会少字段、字段类型会不会漂
    - 看 usage 字段两家有什么差异（DS 有 prompt_cache_hit_tokens，Kimi 没有）

输出会打印每次调用的：raw content（原文）+ stripped json（解析后）+ usage。
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import sys
from dataclasses import dataclass
from pathlib import Path


# 不强依赖项目 settings——脚本要能 standalone 跑
# 简易 .env 解析（避免引 dotenv）
def _load_env(env_path: Path) -> None:
    if not env_path.exists():
        return
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


_load_env(Path(__file__).resolve().parent.parent / ".env")


# ============================================================
# 0. 共同的场景：让模型分类一段话进 inspiration/parenting/mood
# ============================================================

SYSTEM_PROMPT = """你是夕拾的分区路由器。三个分区：
- inspiration（灵感）：想法、创意、产品 idea
- parenting（亲子）：与孩子相关的事件、反思、互动
- mood（心情）：情绪、感受、自我状态

一条输入可属多分区，但必须指定一个主分区（primary）。

只输出合法 JSON，schema：
{
  "primary_zone_id": "inspiration|parenting|mood",
  "zone_ids": ["..."],
  "zone_confidence": {"...": 0.0-1.0},
  "reasoning": "判断理由"
}
"""

TEST_INPUTS = [
    "今天给小宝读了三本绘本，他特别喜欢小猪佩奇",
    "想给孩子做个识字 app，名字叫'夕拾少儿版'",
    "今天好累，什么都不想做",
]


# ============================================================
# 1. Mock 数据（基于 OpenAI 兼容协议 + 各家文档）
# ============================================================

def mock_response(provider: str, user_text: str) -> dict:
    """构造一个 OpenAI 兼容格式的 mock response。"""
    fake_json = {
        "primary_zone_id": "parenting",
        "zone_ids": ["parenting"],
        "zone_confidence": {"parenting": 0.9},
        "reasoning": f"(mock) 输入 '{user_text[:20]}...' 关于孩子",
    }
    content = json.dumps(fake_json, ensure_ascii=False)
    base = {
        "id": f"mock-{provider}-001",
        "model": f"{provider}-mock",
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": content},
                "finish_reason": "stop",
            }
        ],
        "usage": {"prompt_tokens": 120, "completion_tokens": 35, "total_tokens": 155},
    }
    # 各家的 usage 私货
    if provider == "deepseek":
        base["usage"]["prompt_cache_hit_tokens"] = 0
        base["usage"]["prompt_cache_miss_tokens"] = 120
    return base


# ============================================================
# 2. 真实调用
# ============================================================

async def call_real(provider: str, user_text: str) -> dict:
    """真实调用，返回 raw response.model_dump()。"""
    from openai import AsyncOpenAI

    if provider == "kimi":
        client = AsyncOpenAI(
            api_key=os.environ["MOONSHOT_API_KEY"],
            base_url=os.environ.get("MOONSHOT_BASE_URL", "https://api.moonshot.cn/v1"),
        )
        model = "kimi-k2-0905-preview"
    elif provider == "deepseek":
        client = AsyncOpenAI(
            api_key=os.environ["DEEPSEEK_API_KEY"],
            base_url=os.environ.get("DEEPSEEK_BASE_URL", "https://api.deepseek.com"),
        )
        model = "deepseek-chat"
    else:
        raise ValueError(f"unknown provider: {provider}")

    resp = await client.chat.completions.create(
        model=model,
        response_format={"type": "json_object"},
        max_tokens=256,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_text},
        ],
    )
    return resp.model_dump()


# ============================================================
# 3. 观察：strip fence + parse
# ============================================================

FENCE_RE = re.compile(r"^```(?:json)?\s*\n?(.*?)\n?```\s*$", re.DOTALL)

def strip_fence(s: str) -> tuple[str, bool]:
    """返回 (stripped, had_fence)。"""
    m = FENCE_RE.match(s.strip())
    if m:
        return m.group(1).strip(), True
    return s.strip(), False


def observe_one(provider: str, user_text: str, raw: dict) -> None:
    print(f"\n{'─' * 72}")
    print(f"provider = {provider}  |  input = {user_text!r}")
    print(f"{'─' * 72}")

    content = raw["choices"][0]["message"]["content"]
    print(f"raw content ({len(content)} chars):")
    print(content)

    stripped, had_fence = strip_fence(content)
    print(f"\n[fence detected] {had_fence}")

    try:
        parsed = json.loads(stripped)
        print(f"[json parse]    OK")
        print(f"[fields]        {sorted(parsed.keys())}")
        # 类型探测
        for k, v in parsed.items():
            print(f"  - {k}: {type(v).__name__} = {v!r}")
    except json.JSONDecodeError as e:
        print(f"[json parse]    FAIL: {e}")

    print(f"\n[usage] {raw.get('usage')}")


# ============================================================
# 4. main
# ============================================================

async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--real",
        type=str,
        default="",
        help="逗号分隔的 provider 列表，如 kimi 或 kimi,ds。其余走 mock。",
    )
    args = ap.parse_args()

    real_set = {p.strip().replace("ds", "deepseek") for p in args.real.split(",") if p.strip()}

    for provider in ("kimi", "deepseek"):
        print(f"\n\n{'=' * 72}")
        print(f"=== {provider}  ({'REAL' if provider in real_set else 'MOCK'}) ===")
        print("=" * 72)

        for user_text in TEST_INPUTS:
            if provider in real_set:
                try:
                    raw = await call_real(provider, user_text)
                except Exception as e:
                    print(f"\n[ERROR] {provider} call failed: {type(e).__name__}: {e}")
                    continue
            else:
                raw = mock_response(provider, user_text)

            observe_one(provider, user_text, raw)


if __name__ == "__main__":
    asyncio.run(main())
