"""
D6 学习脚本：用 8 条真实输入对 Kimi/DS 各跑一遍 route v2，看：
- 分类一致率（两家对同一输入给出相同 primary_zone_id 的比例）
- 跨分区案例上 confidence 分布是否合理
- 边界案例（叙述焦点 vs 事件类型）是否教会了模型

跑法：
    uv run python experiments/batch_route.py            # 跑 Kimi + DS 各一遍
    uv run python experiments/batch_route.py --model kimi
    uv run python experiments/batch_route.py --model ds

输出：每条输入 × 每家的 RouteResult 一行；末尾给一致率统计。
"""
from __future__ import annotations

import argparse
import asyncio
import sys

# 把 src 加入 path 以便 standalone 跑
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from xishi.service.route import route  # noqa: E402


# 8 条覆盖：单分区 ×3 + 跨 2 分区 ×2 + 跨 3 分区 ×1 + 叙述焦点边界 ×2
TEST_INPUTS = [
    # 单分区基线
    ("纯亲子", "今天给小宝读了三本绘本"),
    ("纯灵感", "突然想到可以做一个把语音直接转成手帐 page 的工具"),
    ("纯心情", "今天阳光特别好，心情也很好"),
    # 跨 2 分区
    ("亲子+灵感", "陪小宝搭乐高时想到一个空间认知 app"),
    ("亲子+心情", "送小宝去幼儿园后突然觉得空荡荡的"),
    # 跨 3 分区
    ("跨 3 分区", "陪小宝画画时想到可以做个 AI 涂色 app，但又觉得累，提不起劲"),
    # 叙述焦点边界（同事件不同主语）
    ("焦点=事件", "小宝今天因为关电视哭了 20 分钟"),
    ("焦点=自己", "小宝今天因为关电视哭了 20 分钟，我真的好烦躁"),
]


async def run_one(model: str, label: str, text: str) -> dict:
    try:
        result = await route(text, model=model)
        return {
            "label": label,
            "text": text,
            "ok": True,
            "primary": result.primary_zone_id,
            "zone_ids": result.zone_ids,
            "confidence": result.zone_confidence,
            "reasoning": result.reasoning,
        }
    except Exception as e:
        return {
            "label": label,
            "text": text,
            "ok": False,
            "error": f"{type(e).__name__}: {e}",
        }


def fmt(r: dict, model: str) -> str:
    if not r["ok"]:
        return f"  [{model}] ❌ {r['error']}"
    primary = r["primary"]
    conf = r["confidence"]
    primary_c = conf.get(primary, 0.0)
    extra = [z for z in r["zone_ids"] if z != primary]
    extra_str = "  ".join(f"{z} {conf[z]:.2f}" for z in extra)
    return (
        f"  [{model:5}] ► {primary} {primary_c:.2f}"
        + (f"  | + {extra_str}" if extra_str else "")
        + f"\n          💭 {r['reasoning']}"
    )


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--model",
        type=str,
        default="both",
        choices=["kimi", "ds", "both"],
        help="跑 kimi / ds / both（默认 both）",
    )
    args = ap.parse_args()

    models = ["kimi", "ds"] if args.model == "both" else [args.model]

    results_by_input: list[tuple[str, str, list[dict]]] = []  # (label, text, [per-model results])

    for label, text in TEST_INPUTS:
        per_model = []
        for m in models:
            r = await run_one(m, label, text)
            per_model.append((m, r))
        results_by_input.append((label, text, per_model))

    # 打印
    print(f"\n{'=' * 76}")
    print(f"D6 batch_route 测试 · prompt v2 · models = {models}")
    print(f"{'=' * 76}")
    for label, text, per_model in results_by_input:
        print(f"\n[{label}] {text}")
        for m, r in per_model:
            print(fmt(r, m))

    # 一致率统计（仅 both 模式有意义）
    if len(models) == 2:
        primary_agree = 0
        zone_set_agree = 0
        total = 0
        for label, text, per_model in results_by_input:
            (m1, r1), (m2, r2) = per_model
            if not (r1["ok"] and r2["ok"]):
                continue
            total += 1
            if r1["primary"] == r2["primary"]:
                primary_agree += 1
            if set(r1["zone_ids"]) == set(r2["zone_ids"]):
                zone_set_agree += 1
        print(f"\n{'─' * 76}")
        print(f"一致率：primary {primary_agree}/{total}  |  zone_ids 集合 {zone_set_agree}/{total}")


if __name__ == "__main__":
    asyncio.run(main())
