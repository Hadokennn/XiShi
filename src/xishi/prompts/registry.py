"""Agent 版本快照——把"影响输出的全部 prompt 侧输入"打成一个不可变对象。

为什么这层存在（参 docs/notes/W1-D6 + 计划中的 W6）：
- prompt caching 命中率验证需要稳定的 prefix 指纹，prefix 任何一字节变 → cache miss
- A/B 实验需要把"被对比的两个版本"和"调用日志"在一个 hash 下绑定，避免归因混乱

设计取舍：
- model 不在 AgentConfig 里——同一 prompt 版本可跨 Kimi/DS 评测；hash 把 model 作为参数
- few_shot 用 tuple[(user_text, assistant_json_str), ...]：assistant 预序列化保证 hash 稳定
- validator 类用 model_json_schema() 序列化进 hash——schema 改了就是新版本
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any, Mapping

from pydantic import BaseModel


@dataclass(frozen=True)
class AgentConfig:
    """一次 Agent 调用的版本快照。frozen=True 防误改。"""

    id: str
    """人类可读标签，例如 'route-v2'。仅用于日志/CLI，不参与 hash。"""

    system: str
    few_shot: tuple[tuple[str, str], ...]
    """(user_text, assistant_json_str) 对。assistant 必须预序列化字符串而非 dict——
    dict 进 frozen dataclass 不可哈希，且 JSON 格式漂移会让 hash 不稳定。"""

    response_format: Mapping[str, Any] | None
    max_tokens: int
    validator: type[BaseModel]

    def build_messages(self, user_text: str) -> list[dict]:
        msgs: list[dict] = [{"role": "system", "content": self.system}]
        for user, assistant_json in self.few_shot:
            msgs.append({"role": "user", "content": user})
            msgs.append({"role": "assistant", "content": assistant_json})
        msgs.append({"role": "user", "content": user_text})
        return msgs

    def build_retry_messages(self, user_text: str, last_raw: str, error: str) -> list[dict]:
        msgs = self.build_messages(user_text)
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

    def prefix_hash(self, model: str) -> str:
        """provider 视角的 cache prefix 指纹——model + system + few-shot。

        真实 user input 不算——它是 messages list 的最后一段，每次都不同。
        cache 命中的是它前面的稳定前缀。
        """
        return _stable_sha(
            {
                "model": model,
                "system": self.system,
                "few_shot": [list(p) for p in self.few_shot],
            }
        )

    def full_hash(self, model: str) -> str:
        """A/B 归因指纹——prefix + 采样参数 + 输出 schema。

        validator 用 JSON Schema 序列化：直接 hash 类对象不稳定（id() 每次进程都变）。
        """
        return _stable_sha(
            {
                "prefix": self.prefix_hash(model),
                "response_format": dict(self.response_format) if self.response_format else None,
                "max_tokens": self.max_tokens,
                "validator_schema": self.validator.model_json_schema(),
            }
        )


def _stable_sha(obj: Any) -> str:
    """canonical JSON → sha256 前 12 位。

    sort_keys 保证字段顺序不影响 hash；ensure_ascii=False 保证中文字节稳定。
    截 12 位（48 bit）够区分实际版本数量，且日志可读。
    """
    s = json.dumps(obj, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(s.encode("utf-8")).hexdigest()[:12]


def few_shot(*pairs: tuple[str, dict]) -> tuple[tuple[str, str], ...]:
    """把 (user_text, assistant_dict) 在源码里写得人话一点，统一在这里序列化。

    在 prompts/<agent>.py 里这么用：
        FEWSHOT = few_shot(
            ("今天好累", {"primary_zone_id": "mood", ...}),
            ...
        )
    """
    return tuple((u, json.dumps(a, ensure_ascii=False)) for u, a in pairs)
