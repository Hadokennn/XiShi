# ADR-0001: 后端技术栈选型

- **状态**：Accepted（2026-05-09 修订：拆分 CLI 入口与 service 层）
- **日期**：2026-05-09
- **决策者**：作者（GAP 期全职 / FE → Agent 全栈转型）

## 背景

夕拾（Xishi）M1 阶段需要一个能在 D45（45 天）内做出 CLI MVP、且能作为面试材料公开展示的后端。约束：

- 作者 FE 出身，Python 仅脚本级，但目标是转 Agent 全栈
- 总预算 195h（投递前）/ 255h（CLI MVP），日均 5h
- 产出要"经得起面试官拷问"——不能黑盒
- 项目核心是多 Agent 编排（Concierge + 分区 Worker + 5 层记忆）

## 决策

| 维度 | 选择 | 替代 |
|---|---|---|
| 语言 | **Python 3.13** | Node.js / Go |
| MVP 入口 | **Typer CLI**（直接 import service 模块，不起 server） | 直接 FastAPI server + httpx 客户端 / Click |
| Service 层 | **普通 async 模块**（`xishi.service.*`，承载领域逻辑） | 把逻辑写进 CLI handler / 写进 FastAPI 路由 |
| HTTP 接口 | **FastAPI（M3 钩子，仅保留 `/health` 占位）** | 不留任何 HTTP 入口 / 现在就铺路由 |
| 数据库 | **Postgres 17 + pgvector** | SQLite + Chroma / Postgres 16 |
| 数据库驱动 | **asyncpg** | psycopg3 / SQLAlchemy ORM |
| 校验 | **Pydantic v2** | dataclass + 手写 / attrs |
| LLM | **Claude Sonnet 4.6（开荒）+ Haiku 4.5（路由）** | OpenAI / Gemini |
| LLM SDK | **`anthropic` SDK 直调** | LangChain / LangGraph / Claude Agent SDK |
| 包管理 | **uv** | pip + venv / Poetry |

## 理由

### 为什么 Python 而不是 Node/Go

- AI/LLM 生态以 Python 为主，绝大多数论文实现、向量检索库、prompt 工具链首发 Python
- 转型目标是 Agent 全栈，Python 是该领域的"母语"
- 作者已有 Python 脚本基础，避免再学一门语言挤压学习预算

### 为什么 Typer CLI 作为 MVP 入口，而不是直接起 FastAPI server

最初版本写的是"FastAPI 作为 Web 框架"，2026-05-09 修订时被自己反问推翻：D60 MVP 是 **CLI**，作者自己用，**没有任何 HTTP 客户端**——起 server 再 curl 它属于纯过度工程。

- **Typer 直接 import service 模块**：CLI handler 调 `await xishi.service.atom.create(...)`，零 HTTP 跳板
- async 跟入口框架无关——Typer 命令体内一样能 `asyncio.run(...)` 跑 anthropic SDK
- 异步装订 = cron 每晚跑一次 `xishi bind`，比常驻 server + APScheduler 简单一个数量级
- Typer 自带子命令解析、help、参数校验，省掉 FastAPI 写路由 + 注册 + 起 server 的样板
- 选 Typer 而非 Click：原生 type hint → 命令签名（与 Pydantic / FastAPI 一脉相承的体验），同作者 tiangolo 维护

替代方案分析：

- **Click**：成熟但要装饰器手写 `@click.option`，type hint 不直接驱动
- **直接起 FastAPI server**：每天调试都要先 `uvicorn`，链路长一截；MVP 阶段没有任何客户端会调它

### 为什么 FastAPI 仍然保留（作为 service 层 + M3 钩子）

不删 FastAPI 的两个理由：

- **M3 加前端/手机端时不用重写**：service 层（`xishi.service.*`）是普通 async 模块，CLI 直接 import；未来 FastAPI 路由也只是另一个 import service 的入口。两套入口共享同一份领域逻辑
- **W1-D2 已写的 `/health` 路由保留为接口骨架**：定位降级为"M3 接口预留"，不在 D60 主路径上展开

边界明确（重要）：

- **D60 之前**：仅保留 `/health`；不写 server 化的 Atom/Concierge 路由
- **M3**：service 层套上 FastAPI 路由 + 前端调用，零改动 service

替代分析：

- Flask 同步阻塞，async LLM 调用浪费连接
- Django 太重，且 ORM 默认同步
- 不用任何 web 框架（纯 service + Typer）：M3 加前端时还得选一次，不如现在锁定

### 为什么 Postgres 17（偏离 roadmap 写的 16）

- Roadmap 写 16 是 2026-04 当时的 latest stable
- 2026-05 装 brew pgvector 时发现 formula 已不再编译给 PG16，仅支持 17/18
- 17 vs 16 对本项目无破坏性差异；跟随社区版本节奏更稳
- pgvector 0.8.2 已支持 HNSW，满足 W5 向量检索需求

### 为什么 asyncpg 而不是 SQLAlchemy ORM

- ORM 黑盒、SQL 不透明，违反"经得起面试拷问"原则
- asyncpg 性能最强（裸 driver），写原始 SQL 反而是面试加分项
- 数据模型只有 7 个实体，不需要 ORM 的复杂关系映射
- 代价：手动管理迁移（接受，本阶段用裸 SQL 文件）

### 为什么裸写而不用 LangChain / LangGraph / Claude Agent SDK

最关键的选型，单独说：

- **LangChain**：抽象层过厚，prompt 黑盒，调试时 stack 深；很多面试官直接问"你 LangChain 实际做了什么"，能答上来的少
- **LangGraph**：状态机抽象本身没问题，但 5 层记忆 + Concierge 调度的逻辑用 graph 表达反而绕
- **Claude Agent SDK**：太新（2025 末发布），用了等于"调 SDK 的人"，没法讲清楚 tool use 循环细节
- **裸写**：代价是写更多代码（约 +40% 行数），收益是每一行都能讲清楚——这恰好是面试最看重的

边界：**Agent 编排 / 记忆 / Prompt 自己写；HTTP / DB / 向量 / 校验用业界标准**。不是为了裸而裸。

### 为什么 uv 而不是 pip+venv 或 Poetry

- uv 是 Rust 写的，安装速度比 pip 快 10-100 倍
- lockfile 机制类似 npm/pnpm，作者 FE 背景熟悉
- 单二进制，无需 Python 环境引导自身（pip 需要先有 Python）
- 已成 2025-2026 Python 社区主流选择

## 后果

**正向**

- 技术栈整条链路 async-native，不会出现"一个同步调用毁掉并发"的问题
- 每个组件都能在面试时讲清楚原理
- 学习路径清晰：W1 三件套（async/Pydantic/Typer + service 分层）→ W2 DB/SDK → W3 schema/pgvector
- CLI/HTTP 边界从 D1 就锁死：领域逻辑只能写在 `xishi.service.*`，CLI 与未来路由都是入口而已

**负向**

- 三个新概念同时上是 W1 最大风险（roadmap 已标记 ⚠️）
- 裸写多 ~40% 代码，时间预算偏紧
- 不用 ORM = 写迁移和复杂查询会更累

**回退方案**

- W3 末仍卡 tool use → 砍 Episodic 简化版至缓冲期
- W6 末压力大 → 心情 Worker 砍到 D46-60
- 整体节奏崩 → 立即降到 4h/天，重谈 timeline
