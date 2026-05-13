"""路由器 prompt——v1。

VERSION 常量为 W6 prompt caching 命中率验证 + 后期 A/B 实验保留版本号。
"""
from __future__ import annotations

import json

ROUTE_PROMPT_VERSION = "route-v1"

ROUTE_SYSTEM_V1 = """你是夕拾的分区路由器。任务：把一条用户随手记入的内容分到三个分区中。

三个分区的语义边界：
- inspiration（灵感）：想法、创意、灵光、产品 idea、读书摘录引发的思考
- parenting（亲子）：与孩子相关的事件、互动、冲突、反思
- mood（心情）：情绪、感受、自我状态（疲惫/焦虑/喜悦/烦躁）

判断规则：
1. 一条输入可属多分区，但必须指定一个主分区（primary_zone_id）
2. zone_ids 列出所有相关分区（含 primary），按相关性降序
3. zone_confidence 给出每个 zone 的置信度（0.0–1.0），可以给 zone_ids 之外的分区分配低软标注
4. reasoning 用一句话解释判断依据

注意：你只做分类，不评论、不建议、不安慰——那是后续 Worker 的事。

只输出合法 JSON，不要 markdown fence，不要多余文字。schema:
{
  "primary_zone_id": "inspiration | parenting | mood",
  "zone_ids": ["..."],
  "zone_confidence": {"...": 0.0-1.0},
  "reasoning": "一句话判断依据"
}
"""

# 3 条 few-shot：覆盖纯单分区、跨分区、心情边界
ROUTE_FEWSHOT_V1: list[dict] = [
    {
        "user": "今天给小宝读了三本绘本，他特别喜欢小猪佩奇",
        "assistant": {
            "primary_zone_id": "parenting",
            "zone_ids": ["parenting"],
            "zone_confidence": {"parenting": 0.95},
            "reasoning": "纯亲子共读场景，没有创意或情绪表达",
        },
    },
    {
        "user": "想给孩子做个识字 app，叫'夕拾少儿版'",
        "assistant": {
            "primary_zone_id": "inspiration",
            "zone_ids": ["inspiration", "parenting"],
            "zone_confidence": {"inspiration": 0.9, "parenting": 0.65},
            "reasoning": "核心是产品创意（主），但明确为孩子设计（亲子相关）",
        },
    },
    {
        "user": "今天好累，什么都不想做",
        "assistant": {
            "primary_zone_id": "mood",
            "zone_ids": ["mood"],
            "zone_confidence": {"mood": 0.95},
            "reasoning": "纯情绪表达，无具体事件或想法",
        },
    },
]


def build_messages(text: str) -> list[dict]:
    """组装一次路由请求的 messages list。

    结构：system → few-shot 三对（user / assistant 各一） → 真实 user input
    """
    msgs: list[dict] = [{"role": "system", "content": ROUTE_SYSTEM_V1}]
    for ex in ROUTE_FEWSHOT_V1:
        msgs.append({"role": "user", "content": ex["user"]})
        msgs.append(
            {"role": "assistant", "content": json.dumps(ex["assistant"], ensure_ascii=False)}
        )
    msgs.append({"role": "user", "content": text})
    return msgs


def build_retry_messages(text: str, last_raw: str, error: str) -> list[dict]:
    """retry 时的 messages：把上次错误结果 + 错误原因塞回，让模型自纠。"""
    msgs = build_messages(text)
    msgs.append({"role": "assistant", "content": last_raw})
    msgs.append(
        {
            "role": "user",
            "content": (
                f"上次输出无法通过校验，错误：{error}\n"
                "请严格按 schema 重新输出合法 JSON，不要添加任何额外字段或文字。"
            ),
        }
    )
    return msgs
