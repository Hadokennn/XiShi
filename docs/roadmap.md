# 路线图：45 天投递 + 60 天 CLI MVP

> 与 `product-vision.md` / `architecture.md` / `data-model.md` 不同——
> 那些是**产品和设计**文档，本文档是**时间表**：什么时候做什么、不做什么、出问题怎么办。

---

## 一、投递目标

- **D45（约 2026-06-21）**：简历 + **GitHub 公开仓库**（含 README + 5+ 篇 ADR + 5 分钟 demo 视频）
- **D60（约 2026-07-06）**：CLI MVP 完整收尾（含缓冲期补做项）

**核心约束**

| 项 | 值 |
|---|---|
| 时长 | 5h/天 × 6 天/周（周日休） |
| 总预算（投递前） | 6.5 周 × 30h = **195h** |
| 总预算（CLI MVP） | 8.5 周 × 30h = **255h** |
| 当前状态 | 用户 GAP 期全职 |
| Python 起点 | 脚本级（async/web/ORM 全是新东西） |
| 实现路线 | 裸写（详见 [feedback memory] 边界） |

---

## 二、6.5 周 × 19 个核心概念

每周聚焦 3 个新概念 + 一个具体产出。**粗体概念**是面试拷问命中率最高的——必须能讲清楚原理、回答跟进问题。

### W1（D1–D7）：Python 后端三件套

- 概念：① **async/await**（事件循环 + coroutine + await 链）② **Pydantic v2** ③ **Typer CLI + service 分层**（领域逻辑写 `xishi.service.*`，CLI 直接 import）
- 产出：100 行 CLI demo（`xishi route "..."` → service 层调 anthropic SDK → Haiku 路由 zone）；FastAPI `/health` 路由作为 M3 接口骨架保留，不在主路径展开
- 风险：⚠️ **三个新概念同时上，整个路线最危险的一周**。W1 末未跑通 → 降到 4h/天，重谈 timeline
- **CLI/HTTP 边界（不可破）**：领域逻辑只写在 service 层；CLI handler 与未来 FastAPI 路由都是入口，不在入口写业务

### W2（D8–D14）：DB + LLM 核心

- 概念：④ **anthropic SDK**（messages / stream / stop_reason） ⑤ asyncpg 连接池 ⑥ Claude 结构化 JSON 输出
- 产出：CLI 能扔 Atom 进 Postgres + Haiku 路由分类

### W3（D15–D21）：Tool Use + Schema

- 概念：⑦ **tool_use / tool_result 协议** ⑧ Postgres schema 设计（外键 / 索引 / JSONB） ⑨ pgvector 基础
- 产出：7 实体简化 schema 全建好；Atom / Cultivation / Zone CRUD 跑通
- **Plan B 决策点**：W3 末仍卡 tool use → 砍 Episodic 简化版（D46–60 补）

### W4（D22–D28）：Concierge 编排

- 概念：⑩ Agent 主循环（multi-turn / stop_reason 分发） ⑪ Prompt 工程（system / few-shot / 结构化输出） ⑫ 错误处理 + 重试 + 降级
- 产出：Concierge 实时通路完整：接住 → 路由 → 写库 → 反馈

### W5（D29–D35）：向量检索

- 概念：⑬ Embedding 选型（voyage-3 vs OpenAI） ⑭ **HNSW 索引**原理 ⑮ 混合检索（关键词 + 向量 + 时间衰减）
- 产出：灵感 Worker 完整开荒 + 调出历史关联 + 核心路径测试

### W6（D36–D42）：异步装订 + 亲子 Worker

- 概念：⑯ 异步任务（**cron + `xishi bind` 命令** vs FastAPI BackgroundTask vs APScheduler——MVP 阶段选 cron 最简） ⑰ **Prompt caching** ⑱ Episodic 简化提取
- 产出：异步装订 CLI 命令（`xishi bind --date today`）；亲子 Worker；Episode 草拟（status=draft）

### W6.5（D43–D45）：投递材料整理

- 概念：⑲ ADR 写作 + 面试 narrative 构造
- 产出：5+ 篇 ADR；5 分钟 demo 视频；README 完善；GitHub 仓库公开

### D46–D60（缓冲期）

按优先级排：

1. 补 W6 因延迟砍掉的功能（如 Episode）
2. 心情 Worker
3. Soul propose 简化版（不做 accept UI）

---

## 三、必砍清单（45 天内不做）

| 砍掉的 | 留下的影子 | 面试时怎么讲 |
|---|---|---|
| 所有前端 / 手机端 | 无 | "M3 计划，本阶段聚焦后端 Agent 架构" |
| Soul accept UI | propose 简化进缓冲期 | "已实现 propose，accept 流是下一步" |
| 隐私脱敏 pipeline | schema 留字段 | "字段已预埋，未来加 redactor" |
| Page 视觉布局 | 简化为文本汇总 | "前端层做布局，后端只输出结构化数据" |
| Share Extension | 无 | "M3 计划" |
| 完整测试覆盖 | 只测核心路径 | 老实说，不藏 |

---

## 四、必保清单（D45 投递时必须有）

- ✅ 三层 Agent 架构 + 裸写编排
- ✅ Tool use 完整循环（自实现，非框架黑盒）
- ✅ Concierge + 1 完整 Worker（灵感）+ 1 简化 Worker（亲子）
- ✅ Postgres + pgvector + HNSW + 混合检索
- ✅ 异步装订 workflow
- ✅ Prompt caching 应用 + 命中率验证
- ✅ 5+ 篇 ADR 在 `docs/adr/`
- ✅ 干净的 commit history（每天 ≥ 1 commit）
- ✅ 5 分钟 demo 视频
- ✅ README 能让陌生人 10 分钟看懂架构

---

## 五、单日 5h 内部结构

```
30 分钟  ─ 复盘昨天 + 读今日资料
[15 分钟休息]
90 分钟  ─ 主推进 1（高认知任务：新概念实操、写核心代码）
[30 分钟休息]
90 分钟  ─ 主推进 2（中认知任务：调试、写测试、重构）
[15 分钟休息]
60 分钟  ─ 收尾：当日笔记 + 明日规划 + 读 1 篇相关博客
```

**纪律**

- ❌ 不允许块 2 连续干 3 小时不休息
- ❌ 不允许跳过收尾的当日笔记
- ✅ 块 2 是认知巅峰窗口，留给当周最难的概念

---

## 六、燃尽红线

GAP 期是燃尽高发期，必须刻意警惕。出现以下任意一条，立即触发对应动作：

| 信号 | 立即动作 |
|---|---|
| 连续 3 天"读不进去"、容易走神 | 当天降到 3h |
| 出现"我在干什么"的迷茫感 | 停 1 天 |
| 周日忍不住想动代码 | 强制完全休息 |
| 进入下一周还在补上一周概念 | 砍当前周第 3 个概念 |
| W1 末身体/心理明显吃力 | 立即降到 4h/天，重谈 timeline |

**核心信念**：**45 天 × 4h 完成 > 30 天 × 5h 然后崩**。

---

## 七、GitHub 公开仓库纪律（D1 起执行）

因为投递路线是 (c) 简历 + 公开仓库，所以从 D1 第一行代码起就要按"公开"标准做：

- D1 第一件事：`git init` + 第一个 commit（项目骨架 + README 草稿）
- 每天至少 1 个可读 commit（不要憋大 PR）
- Commit message 写清楚做了什么、为什么——招聘官会看 history
- README 持续维护（边做边更新，不要等到最后）
- ADR 在 `docs/adr/` 边做边写（每个大决策一篇 200-400 字）
- 学习笔记可放 `docs/notes/`（决定公开与否随时调整）
- 危险信息（API key、本地配置）从 D1 就用 `.env` + `.gitignore` 隔离

---

## 八、每周末 30 分钟自检

每周日休息日的开头花 30 分钟答这三个问题：

1. 这周的 3 个概念，能不能用一句话讲清楚原理 + 一句话讲清楚 trade-off？（讲不出来 → 列入下周补）
2. 这周的产出能不能直接 demo 给一个不懂代码的人看？（不能 → 这周等于没产出）
3. 卡点笔记记齐了吗？（没记 → 当下补）

---

**最后更新**：2026-05-09（W1 入口从 FastAPI server 调整为 Typer CLI + service 分层，详见 ADR-0001 修订节）
