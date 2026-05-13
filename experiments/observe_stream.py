"""
D5 学习脚本：观察 Kimi / DeepSeek 在 stream=True 模式下每个 chunk 长什么样。

跑法：
    uv run python experiments/observe_stream.py              # mock 模式
    uv run python experiments/observe_stream.py --real kimi  # 真实调 Kimi
    uv run python experiments/observe_stream.py --real kimi,ds

目的（observe-before-implement）：
    - 看 chunk.choices[0].delta 的字段：role / content / 谁会是 None
    - 看 finish_reason 在哪一个 chunk 出现（最后一个？倒数第二？）
    - 看 usage 字段什么时候出（流式默认通常不返回 usage，要 include_usage=True）
    - 看两家在 chunk 频率 / 字符密度上的差异
    - 看异常时（短输入、敏感词）流式如何中断

输出：每次调用打印前 5 个 chunk 的完整 dump + 总 chunk 数 + 拼接后的 content。
"""
from __future__ import annotations

import argparse
import asyncio
import os
import time
from pathlib import Path


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


TEST_INPUTS = [
    ("短", "用一句话告诉我天空为什么是蓝色的"),
    ("中", "用 200 字介绍一下 Python 的 async/await 是怎么回事"),
]


def mock_stream(provider: str, prompt: str):
    """假装流式：每 100ms yield 一段中文。"""
    text = f"(mock {provider}) " + ("好的，这是一个模拟流式输出。" * 3)
    for i in range(0, len(text), 4):
        chunk = {
            "id": "mock-chunk-001",
            "model": f"{provider}-mock",
            "choices": [
                {
                    "index": 0,
                    "delta": {"content": text[i : i + 4]} if i > 0 else {"role": "assistant", "content": text[i : i + 4]},
                    "finish_reason": None,
                }
            ],
        }
        yield chunk
    # 最后一个 chunk：finish_reason 出现
    yield {
        "id": "mock-chunk-001",
        "model": f"{provider}-mock",
        "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}],
    }


async def call_real_stream(provider: str, prompt: str, include_usage: bool = True):
    """真实流式调用——返回 (chunks, elapsed_sec, total_content)。"""
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
        raise ValueError(provider)

    kwargs = {
        "model": model,
        "stream": True,
        "max_tokens": 300,
        "messages": [{"role": "user", "content": prompt}],
    }
    if include_usage:
        kwargs["stream_options"] = {"include_usage": True}

    t0 = time.perf_counter()
    chunks: list[dict] = []
    content_parts: list[str] = []

    stream = await client.chat.completions.create(**kwargs)
    async for chunk in stream:
        d = chunk.model_dump()
        chunks.append(d)
        # 提取 delta.content
        try:
            delta_content = d["choices"][0]["delta"].get("content") if d["choices"] else None
        except (IndexError, KeyError, AttributeError):
            delta_content = None
        if delta_content:
            content_parts.append(delta_content)

    elapsed = time.perf_counter() - t0
    return chunks, elapsed, "".join(content_parts)


async def observe(provider: str, real: bool, label: str, prompt: str) -> None:
    print(f"\n{'─' * 72}")
    print(f"provider={provider} ({'REAL' if real else 'MOCK'})  |  {label}: {prompt!r}")
    print(f"{'─' * 72}")

    if real:
        try:
            chunks, elapsed, content = await call_real_stream(provider, prompt)
        except Exception as e:
            print(f"[ERROR] {type(e).__name__}: {e}")
            return
    else:
        chunks = list(mock_stream(provider, prompt))
        elapsed = 0.0
        content = "".join(
            c["choices"][0]["delta"].get("content", "")
            for c in chunks
            if c["choices"] and c["choices"][0]["delta"].get("content")
        )

    print(f"\n[total chunks]   {len(chunks)}")
    print(f"[elapsed]        {elapsed:.2f}s")
    print(f"[content len]    {len(content)} chars")
    print(f"\n[first 3 chunks]")
    for i, c in enumerate(chunks[:3]):
        print(f"  #{i}: {c}")
    print(f"\n[last 2 chunks]")
    for i, c in enumerate(chunks[-2:]):
        print(f"  #{len(chunks)-2+i}: {c}")
    print(f"\n[content preview] {content[:100]}{'...' if len(content) > 100 else ''}")


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--real", type=str, default="")
    args = ap.parse_args()

    real_set = {p.strip().replace("ds", "deepseek") for p in args.real.split(",") if p.strip()}

    for provider in ("kimi", "deepseek"):
        print(f"\n\n{'=' * 72}")
        print(f"=== {provider}  ({'REAL' if provider in real_set else 'MOCK'}) ===")
        print("=" * 72)
        for label, prompt in TEST_INPUTS:
            await observe(provider, provider in real_set, label, prompt)


if __name__ == "__main__":
    asyncio.run(main())
