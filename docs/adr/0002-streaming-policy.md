# ADR-0002: LLM 调用何时流式 / 何时退化为非流式

- **状态**：Accepted
- **日期**：2026-05-14
- **决策者**：作者（GAP 期全职 / W1-D5）

## 背景

D4 把 `xishi route` 跑通后，作者反问："为什么不用打字机效果输出？" 触发本 ADR。

夕拾后续会有多类 LLM 调用：
- `xishi ask`（一次性问 LLM）→ 输出 5–200 行不等，纯文本
- `xishi route`（路由分区）→ 输出固定 schema JSON，需 Pydantic 校验
- `xishi capture`（写 Atom 进 Buffer）→ 短输出，可能含 metadata 抽取
- 异步装订 `xishi bind`（夜间批处理写手帐）→ 长输出，但终端无人观看
- W4 Concierge 主循环 → 多轮对话，含 tool_use stop_reason 分发
- W5 灵感 Worker 开荒 → 长生成 + 关联检索

需要一个**清晰的判断准则**：哪些走流式、哪些不走、原因。否则每加一个命令都要重新讨论一次，且容易写出"流式但每个 chunk 单独 Pydantic 校验"这种自相矛盾的代码。

## 决策

**4 维判断框架**：满足下表 4 个维度的"流式倾向"过半 → 走流式；否则退化为非流式。

| 维度 | 流式倾向 | 非流式倾向 |
|---|---|---|
| **输出长度** | 长（>500 chars 或不可预知） | 短（<200 chars） |
| **结构化要求** | 纯文本 / markdown | 必须 schema 校验（Pydantic / JSON / tool_use 协议） |
| **下游消费者** | 终端用户实时观看 | 机器消费（写库 / 触发后续流程） |
| **延迟敏感度** | 首字延迟（TTFT）比总时长更重要 | 总时长是单一指标 |

### 当前命令分类（明确清单，新加命令要按表更新）

| 命令 | 长度 | 结构化 | 消费者 | 延迟敏感 | 结论 |
|---|---|---|---|---|---|
| `xishi ask` | 长 | ❌ | 终端用户 | ✅ | **流式** |
| `xishi route` | 短 | ✅ Pydantic | 机器（后续写库） | ❌ | **非流式** |
| 未来 `xishi capture` 的 atom 抽取 | 短 | ✅ schema | 机器 | ❌ | **非流式** |
| 未来 `xishi bind` 装订手帐 | 长 | 半结构化 | 机器（写库后展示） | ❌（夜间批处理） | **非流式**（除非加 progress feedback） |
| 未来 Concierge 主循环 | 长 | ✅ stop_reason 分发 | 终端用户 | ✅ | **混合**——文本块流式，工具调用阻塞解析 |
| 未来灵感 Worker 开荒 | 长 | 半结构化 | 终端用户 | ✅ | **流式** |

## 实现约束（来自 D5 observe-before-implement 实测）

跨 provider 的"流式协议方言"（Kimi vs DeepSeek 实测差异）：

| 维度 | Kimi | DeepSeek |
|---|---|---|
| `finish_reason='stop'` 在哪个 chunk | 倒数第 2 | 最后 |
| trailing chunk（`choices=[]`） | ✅ 有 | ❌ 无 |
| 最后有效 chunk 的 `delta.content` | `None` | `''` |
| usage 字段位置 | delta.usage（嵌套）+ trailing chunk 顶层 | 最后 chunk 顶层 |

→ `service/llm.py::ask_stream()` 必须：
1. `if not chunk.choices: continue`（跳 Kimi trailing chunk，否则 IndexError）
2. `if delta.content:`（同时排除 `None` 和 `''`，两家都干净）
3. **不在 service 层暴露 usage**——service 契约只是 `AsyncIterator[str]`；usage / cost 留给未来 `ask_stream_with_usage` 或单独的 telemetry hook

## 为什么不流式 + 结构化校验

技术上可行的三种"流式 + 结构化"路径，全部不选：

1. **等完整 JSON 再 parse**：流式只是 UX 装饰，控制流不变 → 在 route 这种 ~2s 输出场景没收益，徒增 chunk 拼接代码
2. **partial JSON parsing**（如 `partial-json` 库）：解析半截 JSON、边收边校验 → 引入 100+ 行解析状态机，且大部分时间最后 token 才决定 schema 有效性，"提前显示"价值低
3. **放弃结构化、改 markdown 输出**：背离 D4 决策 2（用 Pydantic 校验路由结果）

route 命令 **2-3 秒响应**的可接受焦虑感 << 维护"流式 + 校验"代码路径的复杂度。

## 实现现状（D5）

- `service/llm.py::ask()` 保留为非流式契约，签名不变
- `service/llm.py::ask_stream()` 新增，返回 `AsyncIterator[str]`，跨 Kimi/DS 兼容
- `cli.py::ask` 切到流式（用 `_stream_to_stdout(...)` helper 桥接 Typer 同步外壳）
- `cli.py::route` **未动**——保持非流式
- 用户 Ctrl+C 中断流式：catch `KeyboardInterrupt`，已显示内容不丢，干净退出（exit 130）

## 后果

### 正面
- 终端用户体验：`xishi ask` 首字 <1s 出来，避免 5-10s 无响应
- 决策框架可复用：未来加命令直接查表，不重新论证
- 跨 provider 兼容性已固化为代码注释，下次切 provider 不会重蹈 Kimi trailing chunk 的坑
- 投递材料：ADR + observe 脚本 + 实测 chunk 差异表，是个完整的"我懂流式细节"切片

### 负面
- `service/llm.py` 同时维护 `ask` + `ask_stream` 两个 API → W2 之后若加 `ask_with_usage` / `ask_stream_with_usage`，API surface 会膨胀；届时考虑统一抽象
- `_stream_to_stdout` helper 假定 stdout 终端——未来 FastAPI SSE / WebSocket 消费者要另写桥接，service 层 OK，桥接层每个入口都自己写

## 替代方案（明确拒绝）

- ❌ **全部走流式**：route 等结构化场景实现复杂度暴涨且无收益
- ❌ **全部走非流式**：终端用户体验差，且 W5/W6 长输出场景不可接受
- ❌ **抽象 LLMClient 协议统一 stream/non-stream**：违反 D19（"出现真协议不兼容再抽"），现在抽是 YAGNI

## 待延后

- W6 prompt caching 命中率验证 → 需要 usage 字段 → 那时再决定 `ask_stream_with_usage` 怎么签名
- 流式 + 中途 cancel（不是 Ctrl+C，是主动 abort）→ W4 Concierge 主循环里如果模型走偏要中止，那时再处理
