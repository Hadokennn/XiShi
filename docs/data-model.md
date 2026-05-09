# 数据模型

> **本文档是地基**。这里的字段和决策错了，3 个月后想改会非常痛苦。
> 所有"看起来多余"的字段都有理由，详见每节的"为什么"。

---

## 一、实体关系总览

```
       ┌─────────┐
       │  User   │
       └────┬────┘
            │ owns (owner_id)
   ┌────────┼─────────┬──────────────┬──────────┐
   ▼        ▼         ▼              ▼          ▼
┌──────┐ ┌──────┐ ┌──────────┐ ┌─────────┐ ┌────────┐
│ Zone │ │ Atom │ │ Episode  │ │  Soul   │ │  Page  │
│(分区)│ │(原始)│ │(结构化   │ │ (人格   │ │(每日   │
│      │ │      │ │ 事件)    │ │  记忆)  │ │ 手帐)  │
└──────┘ └──┬───┘ └────┬─────┘ └─────────┘ └────┬───┘
            │          │                         │
            ▼ 1:N      │ N:M atoms              │ N:M atoms+cult
       ┌────────────┐  │                         │
       │Cultivation │  │                         │
       │ (开荒产物) │  │                         │
       └────────────┘  │                         │
            ▲          │                         │
            └──────────┴────── Page 引用 ─────────┘

跨实体关联用 Link 表（多对多 + 类型化）
向量检索用独立 EmbeddingIndex 表
```

### 7 个核心实体一句话总结

| 实体 | 角色 | 谁写 | 可不可改 |
|------|------|------|----------|
| **User** | 用户账号 | 系统 | 部分字段可改 |
| **Zone** | 分区元数据（含 prompt 模板） | 用户 + 系统初始化 | 用户可改 |
| **Atom** | 原始捕获，神圣不可变 | 用户 | 内容不改，状态可变（soft delete） |
| **Cultivation** | AI 对单条/几条 atom 的"开荒产物" | AI | 可重新开荒、可多版本 |
| **Episode** | 结构化事件（育儿命脉） | AI 草拟 + 用户 confirm | 可编辑 |
| **Soul** | 长期人格画像 | AI 提案 + 用户必须 accept | 可编辑、可下线 |
| **Page** | 每日手帐（视觉容器） | AI 装订 | 布局可调 |

---

## 二、7 个 Staff 级关键决策

### 决策 1：Atom 永不真删除 → 任何时候可"重新开荒"

```
Atom: { 
  id, content, status, 
  deleted_at,            # soft delete，UI 隐藏但数据保留
}
Cultivation: { 
  id, atom_id, 
  model_version,         # 用了哪个模型
  prompt_version,        # 用了哪个 prompt 版本
}
```

**为什么：** prompt 会迭代、模型会升级。半年后 prompt 变好了，想拿历史 atom 重新开荒——如果 atom 被改/删，永远做不到。**原始数据是单一权威源（SSOT），所有衍生物都可从原子重建。**

---

### 决策 2：`event_time` ≠ `created_at`，必须分开

```
Atom: { 
  created_at,    # 你按下记录键的时间
  event_time,    # 这件事实际发生的时间
}
```

**为什么：** 核心场景是"晚上记白天发生的事"。如果只有 `created_at`，AI 会以为孩子在晚上 11 点发脾气，时间线全乱。育儿区按"事件时间线"复盘，必须分开。

**UI 行为：** 默认 `event_time = created_at`，但用户可一键改"今天下午"/"昨天晚饭"。语音输入时 AI 可从"今天下午小宝在幼儿园…"自动抽取。

---

### 决策 3：一条 Atom 可属于多个 Zone

```
Atom: {
  zone_ids: [parenting, inspiration],   # array
  primary_zone_id: parenting,            # 主分区，决定开荒模式
  zone_confidence: { parenting: 0.9, inspiration: 0.7 },
  manual_zoned: false,                   # 用户是否手动改过
}
```

**为什么：**
- "我想给孩子做个识字 app" 同时是亲子+灵感+待办——强行单选要么 AI 选错惹用户烦，要么用户被迫拆分一条想法（违反低摩擦输入）
- `manual_zoned` 是 AI 学习的 ground truth——用户手动改过的归类用于微调路由

---

### 决策 4：Episode 是独立实体，不是 Atom 的字段

**反例（错误设计）：** 在 Atom 上加 `reflection`、`next_strategy` 等字段。

**正例（正确设计）：**

```
Episode: {
  id, owner_id,
  atom_ids: [...],         # 由哪些原子构成（可能多条）
  zone_id,                 # 通常 = parenting
  event_time,
  scene,                   # 场景描述
  trigger,                 # 触发因素
  my_reaction,             # 我的反应
  their_reaction,          # 孩子/对方反应
  reflection,              # 事后反思
  next_strategy,           # 下次策略
  people_involved: [...],
  emotion_tags: [...],
  embedding,               # 用于"类似事件"语义检索
  status,                  # draft (AI 草拟) | confirmed (用户确认)
  linked_episodes: [...],  # 关联的历史 episode
}
```

**为什么独立：**
- **一个事件常由多条 Atom 拼成**：你下午随手记一条"小宝又哭了"，晚上又写三段反思——它们应该聚合成一个 Episode
- **Episode 是用户 confirm 过的高质量长期记忆**，质量远高于原始 Atom，应该独立索引、独立检索
- **未来家庭共享时，Episode 才是共享单元**（Atom 是私人草稿，Episode 是双方都认可的事件记录）

**生成时机（决策为 C）：** AI 默认草拟 Episode（status=draft），但**只在用户主动进入"事件复盘"页面时才显示**——日常手帐里不打扰。

---

### 决策 5：Soul 必须 propose → accept，可追溯

```
SoulEntry: {
  id, owner_id,
  category,            # values | patterns | preferences | important_people | sensitivities
  content,
  evidence_atom_ids,   # 这条 soul 是基于哪些原子提炼的（可追溯）
  proposed_by,         # ai | user
  status,              # proposed | accepted | rejected | archived
  created_at,
  last_confirmed_at,   # 用户上次 review 确认这条仍有效
}
```

**为什么：**
- AI 偷偷写 Soul 是信任灾难（用户某天发现 AI 把"我讨厌加班"写成"我热爱工作"，信任直接崩盘）
- `evidence_atom_ids` 让用户能追问"AI 凭啥这么说我"，点进去看到原始证据
- `last_confirmed_at` 让 Soul 有"半衰期"——3 个月没确认的 entry 会被弱化或提醒 review

**Review 时机（决策为每周日）：** 每周日晚上推一次"本周 AI 想加进 soul 的 N 条提案"。

---

### 决策 6：隐私字段从 Day 1 预埋

```
所有用户内容实体都带:
{
  privacy_level,       # 'private' | 'shareable_anon' | 'shareable'
  contains_pii,        # bool, AI 检测到含真实姓名/位置等
  redacted_content,    # text?, AI 生成的脱敏版本（懒加载）
}
```

**为什么：** 不预埋，未来做分享要回填全表，痛。即使 MVP 不做分享，字段必须先有。

---

### 决策 7：家庭共享的"未来钩子"——只加 owner_id，不实现

```
所有内容实体: { owner_id }   # 而不是 user_id
```

**为什么：** 语义上"主人"暗示未来可能有"协作者"。

- **MVP 阶段**：`owner_id` 行为完全等同 `user_id`
- **未来家庭共享**：加一张 `SharedAccess(entity_type, entity_id, shared_with_user_id, permission)` 即可，不动主表

---

## 三、字段速查（MVP 范围）

### Atom（原始捕获）

```typescript
{
  id: uuid,
  owner_id: uuid,
  
  // 时间
  created_at: timestamp,           // 按下记录键的时间
  event_time: timestamp,           // 事件实际发生时间
  
  // 内容
  content: text,                   // 主文本（语音转录后的文字也在这里）
  content_type: enum,              // text | voice_transcript | image | image_with_caption
  voice_url: url?,                 // 语音原文件（可回听）
  image_urls: url[]?,              // 图片
  
  // 分区
  zone_ids: uuid[],                // 可属多区
  primary_zone_id: uuid,
  zone_confidence: jsonb,          // { zone_id: confidence }
  manual_zoned: bool,              // 用户是否手动改过分区
  
  // 元数据
  people_mentioned: string[],      // 提到的人（"小宝"/"妈妈"），AI 抽取
  source: enum,                    // app | share_extension | api
  location: jsonb?,                // 可选 GPS
  mood_signal: string?,            // 输入时的情绪信号
  
  // 隐私（预埋）
  privacy_level: enum,             // private (默认) | shareable_anon | shareable
  contains_pii: bool,
  redacted_content: text?,
  
  // 状态
  status: enum,                    // raw | cultivating | cultivated | archived
  deleted_at: timestamp?,          // soft delete
}
```

### Zone（分区元数据）

```typescript
{
  id: uuid,
  owner_id: uuid,                  // 系统默认分区 owner_id 为 NULL
  name: string,                    // "灵感" / "亲子" / "心情"
  
  // 开荒配置
  prompt_template: text,           // 用户可维护的 prompt
  cultivation_mode: enum,          // expand | socratic | mirror
  
  // 视觉
  display_color: string,
  display_icon: string,
  display_order: int,
  
  is_default: bool,                // 系统初始化的默认分区
}
```

### Cultivation（开荒产物）

```typescript
{
  id: uuid,
  atom_ids: uuid[],                // 通常 1 条，亲子区可能多条
  zone_id: uuid,
  
  created_at: timestamp,
  model_version: string,           // "claude-sonnet-4-6" 等
  prompt_version: string,          // 用了哪个 prompt 版本
  
  content_md: text,                // 开荒后的 markdown
  content_blocks: jsonb,           // 结构化（拓展点/反思问题/子任务等）
  
  related_atom_ids: uuid[],        // 关联的历史原子
  related_episode_ids: uuid[],
  
  status: enum,                    // draft | published | dismissed
  user_feedback: enum?,            // up | down | edited
}
```

### Episode（结构化事件）

见决策 4。

### SoulEntry

见决策 5。

### Page（每日手帐）

```typescript
{
  id: uuid,
  owner_id: uuid,
  date: date,
  
  generated_at: timestamp?,
  status: enum,                    // not_generated | generating | generated
  
  layout: jsonb,                   // AI 生成的布局描述（哪个区在哪、占多大）
  mood_summary: text,              // 今日整体情绪
  
  atom_ids: uuid[],
  cultivation_ids: uuid[],
  
  // 分享（预埋）
  share_token: string?,            // 用于分享
}
```

### Link（跨条目关联）

```typescript
{
  from_type: enum,                 // atom | episode | cultivation | soul
  from_id: uuid,
  to_type: enum,
  to_id: uuid,
  
  link_type: enum,                 // similar_pattern | continuation | contradicts | inspired_by
  strength: float,                 // AI 给的关联强度 0-1
  created_by: enum,                // ai | user
  created_at: timestamp,
}
```

### EmbeddingIndex（向量检索）

```typescript
{
  entity_type: enum,               // atom | episode | soul
  entity_id: uuid,
  vector: vector(1536),            // pgvector
  model: string,
  created_at: timestamp,
}
```

---

## 四、待延后决策

| 决策 | 何时定 |
|------|--------|
| 数据库具体 schema（索引、外键策略） | 开始实现时 |
| 向量维度（取决于选用的 embedding 模型） | 开始实现时 |
| 分片策略（用户量起来后） | 不是 MVP 问题 |
| 备份/恢复策略 | 不是 MVP 问题 |
