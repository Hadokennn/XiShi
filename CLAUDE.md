# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 项目状态：设计阶段（尚无代码）

夕拾（Xishi）目前**只有设计文档，没有任何实现**。本仓库的全部内容是：

```
README.md         # 项目入口
HANDOFF.md        # 每次会话的开场必读
docs/
  product-vision.md   # 痛点 + 定位 + 理念
  architecture.md     # 三层架构 + 5 层记忆 + AI 流程 + 分区开荒
  data-model.md       # 7 个核心实体 + 7 个 staff 级关键决策
  decisions.md        # 已敲定的 20 条决策 + 红线
```

**没有 build/test/lint 命令**——任何想"先跑起来看看"的反应都是错的。技术选型本身（手机端框架、后端语言、API 风格）尚未敲定，见 `HANDOFF.md` 优先级 1 待讨论项。

## 新会话的开场协议

每次进入这个目录，先按顺序读：

1. `HANDOFF.md` — 当前进度、上次停在哪、下次该聊什么
2. `docs/product-vision.md` + `docs/architecture.md` + `docs/data-model.md` — 核心设计三件套
3. `docs/decisions.md` — 仅在你想质疑某个设计时才需要细读

**别急着跳到代码或技术选型**。作者明确说过："很重视设计阶段的细节讨论"。

## 产品形态（决定一切的核心隐喻）

**夕拾 ≠ chat agent，是手帐式第二大脑**。

- chat 是线性流，context 易断（日抛/周抛）
- 手帐是空间化图层（每天一页画布、按分区组织、跨天沉淀）
- AI 角色是**主动开荒**：你白天扔，晚上 AI 装订成手帐，睡前你 review

如果某个建议让产品看起来像 ChatGPT 套壳——**那是错的方向**。

## 架构骨架（写代码前必须内化）

### 三层 Agent

```
Concierge（主调度，唯一入口，全局上下文）
   ↓
分区 Worker（无状态，灵感/亲子/心情，各自独立 prompt 和开荒模式）
   ↕
统一记忆层（Single Source of Truth，所有 Agent 读同一份）
```

**关键反直觉点**：分区**不是 subagent**。subagent 的 context 隔离会断掉跨分区/跨天关联——而"今天孩子又因为同样的事发脾气 → 调出 3 周前那条记录"恰好是产品的灵魂。所以记忆全局共享，分区只承载"加工动作"。

### 五层记忆（按时间衰减 × 内容性质两维度切，不是单维度）

| 层 | 写者 | 读者 |
|----|------|------|
| Buffer（此刻） | 输入入口 | Concierge |
| Today（此页） | Concierge | Concierge 装订手帐 |
| Zone（此区，近 N 天衰减） | 分区 worker | 分区 worker |
| Episodic（结构化事件） | AI 草拟 + **用户 confirm** | 跨天关联、主动提醒 |
| Soul（人格） | AI 提案 + **用户必须 accept** | 全局人格基底 |

### 实时 vs 异步

- **白天实时通路**：只做"接住"——写入 Atom、轻量分类（zone_ids + confidence）、简短确认。**不做开荒**（贵、慢、打扰）
- **晚上异步通路**：批处理装订今日手帐，分区 worker 才在这里跑

## 数据模型不可逾越的 7 条决策

详见 `docs/data-model.md`。最容易被误改的：

1. **Atom 永不真删除（soft delete）**——所有衍生物可从原子重建。这是 SSOT 原则
2. **`event_time` ≠ `created_at`**——晚上记白天事是核心场景，混用会让事件时间线乱
3. **一条 Atom 可属多个 Zone**（`zone_ids` 是 array，配 `primary_zone_id` + `zone_confidence`）
4. **Episode 是独立实体**，不是 Atom 上加字段——多条 Atom 可拼成一个 Episode
5. **Soul 必须 propose → accept**，且带 `evidence_atom_ids` 可追溯
6. **隐私字段从 Day 1 预埋**：`privacy_level` / `contains_pii` / `redacted_content`
7. **用 `owner_id` 而非 `user_id`**——为未来家庭共享留钩子，MVP 行为等同

## 红线（永远不做）

- ❌ **心情区给建议**——共情/镜像/陪伴，不能"你应该…"，会让用户崩溃
- ❌ **AI 偷偷写 Soul**——必须 propose 让用户 accept，否则信任灾难
- ❌ **修改/删除 Atom 的 content**——破坏 SSOT，永远无法重新开荒
- ❌ **手写/涂鸦输入**、**视频输入**——违反低摩擦输入哲学

如果用户的某个新需求会撞这些红线，**先指出冲突**而不是直接实现。

## MVP 范围（已敲定，别擅自扩张）

- 3 个分区：**灵感 / 亲子 / 心情**（**不做待办**——市面太多，稀释定位）
- 输入：**语音 + 文字 + 图片**（图片必须能配 caption）
- 异步装订为主，每周日推 Soul review

## 与作者协作的方式

- **每个推荐都要附理由**——作者讨厌"这是最佳实践"式的空洞回答
- **喜欢深入讨论 trade-off**——别给单一答案，给选项 + 各自代价
- **进入 Plan 模式**讨论非平凡决策（架构、技术选型、数据 schema 改动）
- 作者的全局 CLAUDE.md 强调：简洁优先、根因导向、最小影响——别为了"完整"过度设计

## 当代码开始落地时的检查项

一旦进入实现阶段（目前还没到），新增任何代码前先确认：

- 数据库实体是否符合 `docs/data-model.md` 的 7 条决策（特别是 soft delete、event_time 分离、owner_id）
- 新加的 AI 流程是否符合"实时只接住、异步才开荒"的分工
- 新加的字段是否需要预埋隐私三件套（`privacy_level`/`contains_pii`/`redacted_content`）
- 新加的实体是否带 `owner_id`（不是 `user_id`）
