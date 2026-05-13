"""路由器输出契约。

跟 docs/data-model.md 决策 3「一条 Atom 可属多个 Zone」对齐——
schema 一步到位，prompt few-shot 分阶段教模型用满它。

不带 `manual_zoned`：那是用户层动作（UI 上手动改分区），路由器只负责 AI 推断。
"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, model_validator

ZoneId = Literal["inspiration", "parenting", "mood"]


class RouteResult(BaseModel):
    primary_zone_id: ZoneId
    zone_ids: list[ZoneId] = Field(min_length=1)
    # key 集合允许超过 zone_ids（模型可能给非主分区也打软标注，比如 mood: 0.1）
    zone_confidence: dict[ZoneId, float]
    reasoning: str = Field(min_length=1)

    @model_validator(mode="after")
    def _check_invariants(self) -> "RouteResult":
        if self.primary_zone_id not in self.zone_ids:
            raise ValueError(
                f"primary_zone_id={self.primary_zone_id!r} 不在 zone_ids={self.zone_ids!r} 中"
            )
        missing = [z for z in self.zone_ids if z not in self.zone_confidence]
        if missing:
            raise ValueError(
                f"zone_confidence 缺少 zone_ids 中的: {missing!r}"
            )
        for z, c in self.zone_confidence.items():
            if not 0.0 <= c <= 1.0:
                raise ValueError(f"zone_confidence[{z!r}]={c} 超出 [0, 1]")
        return self
