# HANDOFF — 夕拾（Xishi）

**产品名：** 夕拾  
**项目目录：** `XiShi/`

> 下次会话从这里开始。读完本文件 + `docs/` 五个文档（vision / architecture / data-model / decisions / **roadmap**），就能完整接住上下文。

---

## 项目现状

🚀 **M1 起步阶段**——节奏已锁定，准备 D1 启动。

- 用户当前 **GAP 期全职**，FE → Agent 全栈转型练手 + 面试材料
- Python 起点 = 脚本级（async/web/ORM 等都是新概念）
- **D45（约 2026-06-21）投递节点** = 简历 + GitHub 公开仓库
- **D60（约 2026-07-06）CLI MVP 完整收尾**
- 工作节奏：5h/天 × 6 天/周 = 30h/周；周日完全休息

目录结构：

```
XiShi/
├── README.md              # 项目入口
├── HANDOFF.md             # 本文件
├── CLAUDE.md              # 给未来 Claude 实例的项目指南
└── docs/
    ├── product-vision.md  # 痛点 + 定位 + 理念
    ├── architecture.md    # 三层架构 + 5 层记忆 + AI 流程 + 分区开荒
    ├── data-model.md      # 7 个核心实体 + 7 个 staff 级关键决策
    ├── decisions.md       # 已敲定的所有决策清单（共 20 条）
    ├── roadmap.md         # ★ 45 天投递 + 60 天 CLI MVP 时间表
    ├── adr/               # ★ Architecture Decision Records（边做边写，目标 5+ 篇）
    └── notes/             # ★ 每日学习笔记（按周归档）
```

---

## 已敲定的核心决策（速览）

完整列表见 `docs/decisions.md`。挑最重要的：

**产品**

- 产品形态：手帐式第二大脑，不是 chat agent
- MVP 分区：3 个（灵感 / 亲子 / 心情，**不做待办**）
- 输入模态：语音 + 文字 + 图片（**不做视频**、**不做手写**）
- AI 工作流：异步为主（晚上装订），白天实时只做"接住"

**架构**

- 三层（Concierge + 分区 Worker + 统一记忆层），分区不做 subagent
- 记忆模型：5 层（Buffer / Today / Zone / Episodic / Soul）
- 数据模型 7 大决策：见 `data-model.md` 二节
- 预埋钩子：`owner_id`、`privacy_level`、`source`

**技术栈（已敲定 D1 用的）**

- 后端：**Python 3.13 + Typer CLI（MVP 入口）+ async service 层 + asyncpg + Pydantic v2**
- HTTP 层：**FastAPI 仅保留 `/health` 作为 M3 接口骨架，D60 之前不展开路由**（CLI 直接 import service，不起 server）
- 数据库：**Postgres 16 + pgvector**（HNSW 索引）
- LLM：Claude Sonnet 4.6（开荒）+ Haiku 4.5（路由），通过 `anthropic` SDK 调用
- 编排：**裸写**（不用 LangChain / LangGraph / Claude Agent SDK）
- 前端：**45 天内不做**（投递后 M3 阶段才做）

---

## 红线（不要碰）

- ❌ 心情区给建议
- ❌ AI 偷偷写 Soul（必须 propose → accept）
- ❌ 修改/删除 Atom 的 content（破坏 SSOT）
- ❌ 手写/涂鸦、视频输入

---

## 下一步：W1 D1 启动准备

完整 6.5 周路线见 `docs/roadmap.md`。**W1（D1–D7）核心任务**：

| 概念（学） | 产出（做） |
|---|---|
| ① async / await | 100 行 CLI demo：`xishi route "..."` → service 层调 anthropic SDK → Haiku 路由 zone |
| ② Pydantic v2 | （demo 内含 schema 校验） |
| ③ Typer CLI + service 分层 | CLI handler 直接 import `xishi.service.*`，FastAPI `/health` 已就位作为 M3 钩子 |

**D1 必做的 5 件事**（启动日清单）

1. `git init` + 第一个 commit（项目骨架 + README 草稿）
2. 安装 Python 3.12 + uv（包管理）
3. Postgres 16 + pgvector 在本地跑起来
4. 创建 `.env.example` + `.gitignore`（API key 隔离）
5. 创建 `docs/adr/0001-stack-choice.md`：记录"为什么选 Python + Typer CLI + FastAPI service 分层 + 裸写"

**W1 末 checkpoint**：

- 100 行 demo 跑通 ✓
- 身体心理状态正常 → 继续按 5h/天
- 明显吃力 → 立即降到 4h/天，重谈 timeline

---

## 给下一个 Claude 的提示

1. **必读**：本文件 + `docs/roadmap.md` + `CLAUDE.md`；按需细读 vision / architecture / data-model
2. **memory 路径**：`/Users/aime/.claude/projects/-Users-aime-Documents-inspire-shop-XiShi/memory/`，读一遍 `MEMORY.md` 索引
3. **协作风格**：
   - 全程参与、要解释原理（不是替他写完）
   - 每个技术决策附 trade-off + 替代方案
   - 经得起面试官拷问的深度
4. **节奏纪律**：永远评估"D45 前能否完成"；出现燃尽信号主动建议降时长，不陪用户硬撑
5. **裸写边界**：Agent 编排 / 记忆 / Prompt = 裸写；HTTP / DB / 向量索引 / 校验 = 业界标准。详见 memory `feedback_naked_implementation.md`

---

**最后更新：** 2026-05-09（W1-D2 修订：Typer CLI 取代"直接起 FastAPI server"作为 MVP 入口；FastAPI 降级为 service 层 + M3 钩子。详见 ADR-0001 修订节）
