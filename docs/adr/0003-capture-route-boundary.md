# ADR-0003: capture 与 route 的关系——CLI 命令边界 + Buffer 选型

- **状态**：Accepted（W1 设计层 alignment，实现延后到 W2）
- **日期**：2026-05-15
- **决策者**：作者（GAP 期全职 / W1-D6）

## 背景

D4 把 `xishi route` 跑通后，下一个自然问题：**用户怎么真正记一条进夕拾？** 这就是 `capture` 的位置——它是"输入入口"，负责把一段文字（未来还有语音/图片）变成 Atom 写进 Buffer。

D6 之前从未单独讨论过 capture 跟 route 的关系，结果就是 CLI 已经长出 `xishi route` 这种"测试性命令"——它在生产场景下不会被用户直接调用，因为用户的真实动作是"记录想法"，路由只是副产物。

本 ADR 决定 capture 是什么、跟 route 怎么协作、Buffer 怎么存。W1 不实现（节奏纪律），但接口约定先定，避免 W2 上 DB 时手忙脚乱。

## 决策

### 决策 1：capture 是用户层命令，route 是被复用的领域服务

```
用户视角        CLI 命令              内部调用链
─────────       ─────────             ────────────────────────────────
"记一条"        xishi capture "..." → service.capture.capture()
                                       ├─ service.route.route()  ← 路由结果作为元数据
                                       └─ service.buffer.write_atom() ← 写库

"现在分到哪"    xishi route "..."   → service.route.route()    （测试/调试用）

"问个问题"      xishi ask "..."     → service.llm.ask_stream() （独立通路，不写库）
```

**为什么不让 capture 跟 route 平级**：
- 用户的真实动作是"我要记一条"，不是"我要让 AI 分类"——分类是手段不是目的
- 平级会让用户决策疲劳：每次还要选先 route 再 capture 还是反过来
- route 一旦升级（v2 → v3、加 reasoning_effort），capture 自动继承

**为什么保留 `xishi route` 作为独立 CLI 命令**：
- 调试/演示价值高（D4-D6 整个开发链都靠它）
- 投递材料的 demo 视频里"先纯路由展示分类能力，再 capture 演示完整流程"是经典叙事
- 边际成本极低（service 层共享）

### 决策 2：Buffer = Postgres 表，不走文件 mock 中间态

候选方案对比：

| 方案 | 实现成本 | W2 迁移成本 | 数据一致性 | 是否选 |
|---|---|---|---|---|
| A. 内存 dict | 30 行 | 重写 0 % | ❌ 进程退出丢失 | ❌ |
| B. JSONL 文件 mock | 50 行 | 高（schema 迁移、字段映射） | 🟡 单进程 OK | ❌ |
| C. Postgres asyncpg 直写 | 100 行 + DB schema | 0 % | ✅ 事务 + 索引 | ✅ |

D6 选 **C** 但 **W2 才动手**——W1 已经偷过流式 + Pydantic，不能再偷 DB。本 ADR 是"设计 + 接口约定"，写代码留 W2 D8。

**为什么不用 B（JSONL mock）**：B 看似省事，但：
- 写一遍 JSONL 序列化、再 W2 写一遍 asyncpg 插入 = **写了两遍**
- 字段类型在 JSONL 是字符串、在 PG 是 UUID/timestamp/jsonb——迁移时所有 caller 改一遍
- 中间态代码进 git history 后被未来读者认为是"故意分层"，维护成本反而上升
- **关键反直觉**：mock 不是省事，是债

### 决策 3：service.capture 的接口签名（W2 实现前的硬约定）

```python
# src/xishi/service/capture.py（W2 实现，D6 仅约定）

from xishi.schemas.atom import Atom, AtomDraft   # W2 增 schemas/atom.py
from xishi.schemas.zone import RouteResult


async def capture(
    text: str,
    *,
    owner_id: UUID,
    event_time: datetime | None = None,   # 默认 = now()
    source: Literal["cli", "voice", "share"] = "cli",
    model: str = "ds",
) -> Atom:
    """
    入口契约：
    - 写一条 Atom 到 Buffer（status=raw）
    - 路由结果直接落到 Atom 的 primary_zone_id / zone_ids / zone_confidence 三字段
    - 写库后返回完整 Atom（含 id / created_at）

    不做：
    - 不做开荒（cultivation 是 W4-W5 异步任务）
    - 不做 Episode 草拟（W6+ 异步）
    - 不做 embedding 计算（W5）——只写主表，向量索引 W5 单独 job 回填
    """
    ...
```

**关键设计点**：
- `event_time` 跟 `created_at` 分开（data-model.md 决策 2）——capture 的 `event_time` 默认 = now，但 CLI 后期可加 `--time "今天下午"` 让 AI 抽取
- `source` 字段从 D1 起埋好（decisions.md D5 共享钩子），CLI 调用就传 `"cli"`
- 默认 `model="ds"`：D5 末作者把 route default 从 kimi 切回 ds——本 ADR 跟随
- 不暴露 RouteResult 给 caller——路由是内部细节，caller 拿到的是 Atom

### 决策 4：CLI 命令的最终矩阵（W2-W3 完成）

| 命令 | 状态 | service 调用 | 何时实现 |
|---|---|---|---|
| `xishi ask` | ✅ D5 | `service.llm.ask_stream` | 已完成 |
| `xishi route` | ✅ D4 | `service.route.route` | 已完成（保留作调试） |
| `xishi capture "..."` | 待 W2 | `service.capture.capture` | W2 D8-D10 |
| `xishi ls` | 待 W3 | `service.atom.list` | W3 D15+ |
| `xishi bind` | 待 W6 | `service.bind.bind_today` | W6 D36+ |

## 不在本 ADR 范围内

- ❌ DB schema 细节（外键、索引）→ W2 D8 实现时定，本 ADR 只约定 Python 接口
- ❌ 语音转文字 pipeline → 不是 MVP，CLI 阶段不做
- ❌ 图片 caption pipeline → 同上
- ❌ AtomDraft 跟 Atom 是不是要拆 → W2 写代码时再判断（YAGNI）

## 后果

### 正面
- W2 D8 写 `service.capture.capture` 时签名已敲定，省一次"该怎么设计"的纠结
- `xishi route` 留在仓库的合理性被显式记录——投递时招聘官不会问"为什么有两个看似重复的命令"
- Buffer 直上 Postgres 避免 JSONL mock 这条死巷

### 负面
- W1 末作者会看到一个**只设计未实现的 capture** 留在 `docs/` 里——可能心痒——必须忍住到 W2
- 决策 2 拒绝了 JSONL mock = W1 末没有"完整闭环 demo"（demo 只能演 ask + route + 设计图，不能演 "记一条进库"）

## 替代方案（明确拒绝）

- ❌ **把 route 收进 capture，删掉 `xishi route` CLI**：调试价值 + demo 价值 > 一个命令的维护成本
- ❌ **capture 既写 Atom 又跑 cultivation**：违反 architecture.md 「实时只接住、异步才开荒」铁律
- ❌ **W1 用 JSONL mock 把 capture 跑通**：见决策 2 拒绝理由——mock 是债不是省事

## 待延后

- W2 实现时确认：`Atom.id` 是数据库生成（DEFAULT gen_random_uuid()）还是应用层生成（`uuid7`）→ asyncpg 实测后决定
- W3 决定：`xishi ls` 的过滤参数（按 zone / event_time / status）
- W4 决定：cultivation 触发时机（即时 vs 异步 job）
