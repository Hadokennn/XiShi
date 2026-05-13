"""路由 service：把"自由文本"分类到夕拾的三个分区，返回结构化 RouteResult。

边界（同 service/llm.py 契约）：
- 输入：纯字符串 + 模型别名
- 输出：纯 Pydantic 对象（RouteResult）
- 不打印、不感知谁在调（CLI / FastAPI / cron 都行）
- 解析失败 retry 一次；两次都失败 → raise RouteParseError，含 raw 与 pydantic 错误链
"""
from __future__ import annotations

import json
import re

from pydantic import ValidationError

from xishi.prompts.route import build_messages, build_retry_messages
from xishi.schemas.zone import RouteResult
from xishi.service.llm import MODELS, _client_for

_FENCE_RE = re.compile(r"^```(?:json)?\s*\n?(.*?)\n?```\s*$", re.DOTALL)


class RouteParseError(RuntimeError):
    """两次尝试后仍无法解析模型输出为 RouteResult。

    携带：
    - raw_first / raw_second：两次原文
    - last_error：最后一次的错误描述
    """

    def __init__(self, raw_first: str, raw_second: str | None, last_error: str) -> None:
        super().__init__(
            f"路由解析失败（已重试 1 次）：{last_error}\n"
            f"raw_first: {raw_first!r}\n"
            f"raw_second: {raw_second!r}"
        )
        self.raw_first = raw_first
        self.raw_second = raw_second
        self.last_error = last_error


def _strip_fence(s: str) -> str:
    """D4 observe 显示 Kimi/DS 都不塞 fence，但留作防御。"""
    m = _FENCE_RE.match(s.strip())
    return m.group(1).strip() if m else s.strip()


def _parse(raw: str) -> RouteResult:
    """raw → stripped → json → Pydantic。任一步抛出由调用方处理。"""
    stripped = _strip_fence(raw)
    payload = json.loads(stripped)
    return RouteResult.model_validate(payload)


async def route(text: str, model: str = "kimi") -> RouteResult:
    if not text.strip():
        raise ValueError("text 不能为空")
    if model not in MODELS:
        raise ValueError(f"unknown model alias: {model!r}, available: {sorted(MODELS)}")

    cfg = MODELS[model]
    client = _client_for(cfg.provider)

    # 第一次
    resp1 = await client.chat.completions.create(
        model=cfg.model_id,
        response_format={"type": "json_object"},
        max_tokens=512,
        messages=build_messages(text),
    )
    raw1 = resp1.choices[0].message.content or ""

    try:
        return _parse(raw1)
    except (json.JSONDecodeError, ValidationError) as e1:
        # retry 一次，把错误带回去
        err1 = f"{type(e1).__name__}: {e1}"
        resp2 = await client.chat.completions.create(
            model=cfg.model_id,
            response_format={"type": "json_object"},
            max_tokens=512,
            messages=build_retry_messages(text, raw1, err1),
        )
        raw2 = resp2.choices[0].message.content or ""

        try:
            return _parse(raw2)
        except (json.JSONDecodeError, ValidationError) as e2:
            raise RouteParseError(raw1, raw2, f"{type(e2).__name__}: {e2}") from e2
