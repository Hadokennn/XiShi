# W1-D2 学习笔记：五家 LLM API 真实差异 + Vercel AI SDK 抹平了什么

> 配套脚本：[`experiments/llm_provider_diff.py`](../../experiments/llm_provider_diff.py)
>
> 跑法：
> ```bash
> uv run python experiments/llm_provider_diff.py                     # 全 mock
> uv run python experiments/llm_provider_diff.py --real deepseek,kimi # 这俩真实调
> ```

## 起因

ADR-0001 锁了 Anthropic 主力 + 裸写 SDK。但 D2 自己反问：「Vercel AI 不是已经抹平差异了吗？」表格说服不了自己——必须把 raw response 摊在屏幕上才会真懂。

## 段 0：能力总览（先看这层，再深入协议）

协议差异讲的是"怎么传消息"，**能力差异才是"这家能做什么别家做不了"**——后者比前者更影响选型。

### 各家招牌能力对照

| 厂商 | 招牌能力 | 对夕拾的相关度 |
|---|---|---|
| **Anthropic** | • **Prompt caching 显式控制**（`cache_control` 最多 4 个 break points + 1h TTL + 独立计费：写 1.25x / 读 0.1x）<br>• **Extended thinking**（`budget_tokens` 控思考预算 + 独立 block）<br>• **Tool use block-level**（parallel tool calls + `tool_choice` 精控）<br>• **Batch API**（50% 折扣，24h 内出）<br>• Computer use / MCP / PDF 原生 / Files + Citations | 🟢 W6 caching + W4 tool use 主战场 |
| **OpenAI** | • **Structured outputs**（严格 JSON schema，比 tool use 轻量）<br>• **Realtime API**（语音 duplex 流）<br>• **Reasoning effort**（o 系列：`low/medium/high`）<br>• Logprobs / Image gen / Operator / Assistants | 🟡 Structured outputs 概念可借鉴 |
| **DeepSeek** | • **自动前缀缓存**（无 SDK 控制，input 命中部分降到 ~10% 价）<br>• **价格屠夫**（~$0.27/M input、$1.10/M output）<br>• DeepSeek-R1（开源 reasoning，weight 可下载）<br>• 代码模型强 | 🟡 W1–W2 试错调用便宜，但 caching 不可控 |
| **Moonshot/Kimi** | • **超长上下文**（K2 达 2M tokens）<br>• **上下文缓存 cache_id**（**手动**管理，比 DeepSeek 自动更可控）<br>• **Partial mode**（强制模型续写指定前缀，prefill）<br>• Kimi K2 万亿参数 MoE | 🟡 cache_id 心智跟 Anthropic 的 cache_control 最接近 |
| **千问/Qwen** | • **视频理解原生**（qwen-vl）<br>• thinking 模式（`reasoning_content` 字段）<br>• **开源 weight**（Qwen3 全系列）<br>• 阿里云生态深度（DashScope） | 🔴 视频/阿里生态对夕拾用不上 |

### 三个对夕拾最重要的差异点

**1. Caching 不是"有没有"，是"控不控得住"**

- DeepSeek：自动，只看到 hit/miss 计数，**无法决定哪里切 cache 边界**
- Kimi：可手动 `cache_id`，但只能整段 cache，**没有 multi-breakpoint**
- Anthropic：一次 prompt 内最多 4 个 `cache_control` 标记，精确控制 system / few-shot / 工具定义分别 cache

为什么对夕拾要紧：W6 「Prompt caching 命中率验证」——Anthropic 能写出"system 部分 95% 命中 / few-shot 部分 80% 命中"的实验，DeepSeek 只能写"今天平均命中 60%"。**面试可讲性差一个量级**。

**2. Tool use 协议的表达力**

- OpenAI 系：`content` 和 `tool_calls` 二选一（一回合要么说话要么调工具）
- Anthropic：block 数组可穿插（说一句 → 调工具 → 再说一句 → 再调工具）

为什么对夕拾要紧：Concierge 主调度天然是"先回应用户 → 调分区 Worker → 再回应用户"——Anthropic block 模型一次响应搞定，OpenAI 协议要拼三轮 message。

**3. Thinking 是不是独立维度**

- Anthropic：`thinking` block 在 content 数组里，单独可 trace
- OpenAI o 系列：reasoning tokens 只计数不可见
- 千问/DeepSeek：`reasoning_content` 字段（拿得到文本，但跟 text 平级）

对夕拾：W4 调试 Concierge prompt 时，能直接读"模型在想什么"是降维打击。

### 一句话总结

ADR-0001 选 Anthropic 主力**不是因为模型质量**（旗舰款这几家都够用），是因为**上面三个能力差异恰好是面试 Agent 岗位最爱拷问的点**。换其他家不是不能做，是讲不出 Anthropic-only 的深度。

## 段 1：协议根的两大流派

跑脚本段 1 看到的 raw 字段，本质上分两派：

### 流派 A：Anthropic 的 block-level 设计

```jsonc
{
  "content": [
    {"type": "text", "text": "我帮你查询北京的天气。"},
    {"type": "tool_use", "id": "toolu_01XYZ", "name": "get_weather", "input": {...}}
  ],
  "stop_reason": "tool_use",
  "usage": { "input_tokens": 423, "cache_creation_input_tokens": 0, ... }
}
```

**核心心智**：一次响应是一个 **block 数组**，text / tool_use / thinking 都是平级 block 类型。模型可以"先说一句话 → 再调工具 → 再说一句话"，顺序自然由数组保留。

### 流派 B：OpenAI 系的 message-level 设计（含 DeepSeek / Kimi / 千问兼容模式）

```jsonc
{
  "choices": [{
    "message": {
      "role": "assistant",
      "content": null,                   // ← 要么文本，要么 null
      "tool_calls": [                    // ← 工具调用是 message 上的字段
        {"id": "call_abc", "function": {"name": "get_weather", "arguments": "{\"city\":\"Beijing\"}"}}
      ]
    },
    "finish_reason": "tool_calls"
  }]
}
```

**核心心智**：一次响应是**一个 message**，工具调用作为 message 的字段挂载。文本和工具调用**不在同一维度**——`content` 是字符串，`tool_calls` 是数组，二者并列。

### 一句话差异

- Anthropic：**"AI 这一回合做了什么"是一串 block**
- OpenAI 系：**"AI 这一回合是一条带工具字段的消息"**

后果：Anthropic 协议下"模型先解释再调工具，再解释一句"是自然写法；OpenAI 协议下要么 `content + tool_calls` 二选一，要么走多轮 message 拼接。

### 国产三家的细微差异

跑脚本你会看到 DeepSeek/Kimi 的 raw 几乎和 OpenAI 一字不差，只在 `usage` 里加私货：

| 厂商 | usage 多出的字段 | 含义 |
|---|---|---|
| DeepSeek | `prompt_cache_hit_tokens` / `prompt_cache_miss_tokens` | 自动前缀缓存命中情况 |
| Kimi | （手动 cache 模式才有 `cache_id`） | 显式上下文缓存 |
| 千问 | `message.reasoning_content` | 思考链文本（开 thinking 时） |

**真实跑 `--real deepseek,kimi` 验证一下你 .env 里的两家是不是真这样**——脚本 mock 是按文档构造的，但厂商可能更新过字段。

## 段 2：Vercel AI SDK 风格归一化做了什么

脚本段 2 把所有家归到同一个 dataclass：

```python
@dataclass
class UnifiedResponse:
    text: str | None
    tool_calls: list[UnifiedToolCall]   # name + args + raw_id
    finish_reason: Literal["stop", "tool_calls", "length"]
    usage: UnifiedUsage                  # prompt_tokens + completion_tokens
```

跑完会发现：**输出长得一模一样**。这就是 SDK 的卖点——你写应用代码不用关心是哪家。

它做的两件事：

1. **结构归一**：Anthropic 的 block 数组 → 平铺成 `text + tool_calls`；OpenAI 的 `tool_calls` 字段 → 提取成同样的 list
2. **值域归一**：Anthropic 的 `stop_reason: "end_turn"` 和 OpenAI 的 `finish_reason: "stop"` 映射到同一个枚举

看脚本里 `normalize_anthropic` 和 `normalize_openai_compat` 两个函数——**这就是 Vercel AI SDK / LangChain 等抽象层做的事**。逻辑不复杂，30 行能写完核心。

## 段 3：抹平的代价（脚本最后一段）

归一化看起来很美，但每个被丢的字段都对应一个具体场景会咬人：

### Anthropic 端的损失（对夕拾最致命）

| 丢失字段 | 何时咬人 |
|---|---|
| `usage.cache_creation_input_tokens` | **W6 必保项**——Prompt caching 命中率验证依赖这个，没了等于"我不知道我的 caching 有没有工作" |
| `usage.cache_read_input_tokens` | 同上，且这俩计费不同（写 cache 1.25x、读 cache 0.1x） |
| content 数组里的**穿插顺序** | 模型"边说边调工具"的能力被削平——本来你能从顺序看出"模型先思考再行动还是边行动边解释" |
| extended thinking block | 思考链被合并进 text，无法单独 trace（W4 调试 prompt 时关键） |

### 共同损失

- `stop_reason` 原始字符串 → 归一化后值域压缩到 3 个，丢失 `pause_turn` / `refusal` 等细分
- `model` 字段的精确版本号 → 排查"OpenAI 悄悄把我的 gpt-4 替换成 gpt-4-turbo"时没线索
- 流式细节（脚本未演示）→ Anthropic 的 `content_block_delta` 按 block 类型分流，归一化后只有扁平 text chunks

### 对夕拾的判断（链回 ADR-0001）

夕拾的核心面试卖点：

- **W3** "tool_use / tool_result 协议自实现" ← 用归一化层就没法讲细节
- **W6** "Prompt caching 命中率验证" ← 归一化层把 cache 字段吞了，**这条直接死**
- **W4** Concierge 主循环（按 stop_reason 分发） ← 值域被压成 3 个就讲不出"为什么 pause_turn 要单独处理"

所以 ADR-0001 的"裸写边界"延伸到这里：**LLM 调用层不能用 Vercel AI SDK / LangChain，跟当初拒绝 LangChain 同一个理由**——抽象层抹平的恰好是面试官最爱拷问的部分。

但**业务项目可以用**：如果只是给客户做个 chatbot、不在乎细节、需要快速切换模型——Vercel AI SDK 是合适的。**只是不适合"作为面试材料的项目"**。

## 段外：什么时候归一化是对的

不是反对所有抽象，反对的是"在还没理解协议根之前就用抽象"。判断标准：

- ✅ 你能讲清楚 Anthropic block-level vs OpenAI message-level 的差异 → 用任何抽象都 OK
- ❌ 你只会用 `client.chat.completions.create()` → 先裸写一遍再说

夕拾走的是后者：先裸写打底，**M3 真上前端时**如果想加多 provider 支持再考虑抽象层。

## 收获 checklist（W1 末自查）

- [ ] 能用一句话讲清楚 Anthropic 和 OpenAI tool use 协议的根差异
- [ ] 能默写出归一化层 30 行核心代码
- [ ] 能列出 3 个被归一化吞掉的关键字段 + 各自咬人场景
- [ ] 跑过 `--real deepseek,kimi` 看真实 raw（mock 是按文档构造的，可能落后）

---

**最后更新**：2026-05-09（D2，本日反问 ADR-0001 后产出）
