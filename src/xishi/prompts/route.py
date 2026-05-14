"""路由器 prompt 版本表。

每代 prompt 改动 → 新增 AgentConfig 实例 + 注册到 ROUTE_CONFIGS。
**不要原地改老版本**——A/B 实验和 cache 命中率验证都需要旧版本可被对照。

v1 → v2 改动（W1-D6）：
- few-shot 从 3 例扩到 5 例，新增跨 3 分区案例 + 心情主带亲子要素的边界案例
- system 加判断原则 4：「主分区跟用户叙述焦点，不跟事件类型」
"""
from __future__ import annotations

from xishi.prompts.registry import AgentConfig, few_shot
from xishi.schemas.zone import RouteResult

# ────────────────────────────── v1（W1-D4） ──────────────────────────────

_ROUTE_SYSTEM_V1 = """你是夕拾的分区路由器。任务：把一条用户随手记入的内容分到三个分区中。

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

_ROUTE_FEWSHOT_V1 = few_shot(
    (
        "今天给小宝读了三本绘本，他特别喜欢小猪佩奇",
        {
            "primary_zone_id": "parenting",
            "zone_ids": ["parenting"],
            "zone_confidence": {"parenting": 0.95},
            "reasoning": "纯亲子共读场景，没有创意或情绪表达",
        },
    ),
    (
        "想给孩子做个识字 app，叫'夕拾少儿版'",
        {
            "primary_zone_id": "inspiration",
            "zone_ids": ["inspiration", "parenting"],
            "zone_confidence": {"inspiration": 0.9, "parenting": 0.65},
            "reasoning": "核心是产品创意（主），但明确为孩子设计（亲子相关）",
        },
    ),
    (
        "今天好累，什么都不想做",
        {
            "primary_zone_id": "mood",
            "zone_ids": ["mood"],
            "zone_confidence": {"mood": 0.95},
            "reasoning": "纯情绪表达，无具体事件或想法",
        },
    ),
)

ROUTE_V1 = AgentConfig(
    id="route-v1",
    system=_ROUTE_SYSTEM_V1,
    few_shot=_ROUTE_FEWSHOT_V1,
    response_format={"type": "json_object"},
    max_tokens=512,
    validator=RouteResult,
)

# ────────────────────────────── v2（W1-D6） ──────────────────────────────

_ROUTE_SYSTEM_V2 = """你是夕拾的分区路由器。任务：把一条用户随手记入的内容分到三个分区中。

三个分区的语义边界：
- inspiration（灵感）：想法、创意、灵光、产品 idea、读书摘录引发的思考
- parenting（亲子）：与孩子相关的事件、互动、冲突、反思
- mood（心情）：情绪、感受、自我状态（疲惫/焦虑/喜悦/烦躁）

判断规则：
1. 一条输入可属多分区，但必须指定一个主分区（primary_zone_id）
2. zone_ids 列出所有相关分区（含 primary），按相关性降序
3. zone_confidence 给出每个 zone 的置信度（0.0–1.0），可以给 zone_ids 之外的分区分配低软标注
4. **主分区跟用户的叙述焦点，不跟事件类型**——同一件事用"我累了"和"孩子哭了"表达，主分区可能不同
5. reasoning 用一句话解释判断依据

注意：你只做分类，不评论、不建议、不安慰——那是后续 Worker 的事。

只输出合法 JSON，不要 markdown fence，不要多余文字。schema:
{
  "primary_zone_id": "inspiration | parenting | mood",
  "zone_ids": ["..."],
  "zone_confidence": {"...": 0.0-1.0},
  "reasoning": "一句话判断依据"
}
"""

# 5 条 few-shot：单分区 ×3 + 跨 2 分区 ×1 + 跨 3 分区 ×1 + 心情主带亲子要素 ×1
# 设计意图见 docs/notes/W1-D6.md「prompt v2 设计逻辑」节
_ROUTE_FEWSHOT_V2 = few_shot(
    (
        "今天给小宝读了三本绘本，他特别喜欢小猪佩奇",
        {
            "primary_zone_id": "parenting",
            "zone_ids": ["parenting"],
            "zone_confidence": {"parenting": 0.95},
            "reasoning": "纯亲子共读场景，没有创意或情绪表达",
        },
    ),
    (
        "想给孩子做个识字 app，叫'夕拾少儿版'",
        {
            "primary_zone_id": "inspiration",
            "zone_ids": ["inspiration", "parenting"],
            "zone_confidence": {"inspiration": 0.9, "parenting": 0.65},
            "reasoning": "核心是产品创意（主），但明确为孩子设计（亲子相关）",
        },
    ),
    (
        "今天好累，什么都不想做",
        {
            "primary_zone_id": "mood",
            "zone_ids": ["mood"],
            "zone_confidence": {"mood": 0.95},
            "reasoning": "纯情绪表达，无具体事件或想法",
        },
    ),
    (
        "今天陪小宝玩积木，突然想到可以做个空间感训练 app，但又觉得太累不想动手",
        {
            "primary_zone_id": "inspiration",
            "zone_ids": ["inspiration", "mood", "parenting"],
            "zone_confidence": {"inspiration": 0.85, "mood": 0.6, "parenting": 0.5},
            "reasoning": "核心是产品创意（主），叠加疲惫情绪与亲子场景，三分区同时触发",
        },
    ),
    (
        "小宝今天又因为关电视哭了 20 分钟，我真的好烦躁",
        {
            "primary_zone_id": "mood",
            "zone_ids": ["mood", "parenting"],
            "zone_confidence": {"mood": 0.85, "parenting": 0.7},
            "reasoning": "叙述焦点是用户的烦躁情绪（主），亲子冲突是触发因素",
        },
    ),
)

ROUTE_V2 = AgentConfig(
    id="route-v2",
    system=_ROUTE_SYSTEM_V2,
    few_shot=_ROUTE_FEWSHOT_V2,
    response_format={"type": "json_object"},
    max_tokens=512,
    validator=RouteResult,
)

# ────────────────────────────── 注册表 ──────────────────────────────

ROUTE_CONFIGS: dict[str, AgentConfig] = {
    ROUTE_V1.id: ROUTE_V1,
    ROUTE_V2.id: ROUTE_V2,
}

DEFAULT_ROUTE_VERSION = ROUTE_V2.id
