# W1-D3 教案：anthropic SDK + Typer CLI + service 层雏形

- **日期**：2026-05-11（W1-D3）
- **预计用时**：5h（30min 复盘 + 90min 概念 / 答题 + 90min 实战 + 60min 收尾）
- **前置**：W1-D1 概念巩固 + W1-D2 src layout / FastAPI `/health` 跑通

---

## 0. 今日定位

W1 末（D7）的目标产出是 **"100 行路由 demo：anthropic SDK + Haiku 路由 zone"**。
按 ADR-0001 修订后的架构，"路由"指的是 **Typer CLI 命令** `xishi route "..."`，不是 FastAPI 路由。

D3 是这个产出的第一步：**让 anthropic SDK 在本地调通一次 Haiku，并落到 service 层架子里**。今天**不要求**已经能做 zone 分类——只要求：

1. 调一次 Haiku 拿到响应（任何 prompt 都行）
2. 把响应**完整 dump 出来观察**，建立对 anthropic SDK 响应结构的肌肉记忆
3. 把调用封装到 `xishi.service.llm` 模块
4. 写第一个 Typer CLI 命令 `xishi ask "..."`，把 service 层调通

zone 分类的 prompt 工程留给 D4。

---

## 0.1 关于 W1-D2 写的 FastAPI `/health`——它白做了吗？

**没白做**。按修订后的 ADR-0001，FastAPI 的定位变了：

- D60 之前的**主路径**是 Typer CLI
- FastAPI 仅保留 `/health` 作为 **M3 加前端/手机端时的接口骨架预留**
- D2 你已经验证了"FastAPI + Pydantic Settings + uvicorn"这条链路能跑——M3 接入时不会再从零踩坑

换句话说：D2 的 FastAPI 是**未来要用的备胎已经验证好了**，今天 D3 起把主油门切到 Typer CLI 这条路。两条路共享同一份 `xishi.service.*` 领域逻辑。

---

## 0.2 LLM Provider 修订：主线改为 Kimi（OpenAI 兼容）

本教案最初按"主线 Anthropic SDK"写。**修订后的决策见 [decisions.md#D19](../decisions.md)**：

- **主线**：Kimi K2（Moonshot），通过 OpenAI 兼容协议（`openai` SDK + 自定义 `base_url`）调用。理由：成本约 1/5、国内 Agent 岗主流、agentic 能力够用
- **学习对比**：D3 实战仍 dump **一次 Anthropic 响应**做对比观察。两个 provider 的 response schema 完全不同——OpenAI 的 `choices[0].message.content` vs Anthropic 的 `content[*].type='text'.text`——亲手对比一遍才能建立跨范式肌肉记忆。这是面试拷问"为什么 Anthropic 用 content blocks 而非 chat completions"时的弹药库
- **抽象口子**：D3 **不**预先抽象 `LLMClient` 协议。先 hardcode Kimi 调通，W2 service 层稳定后再加（避免过度设计，违反"简洁优先"红线）

下面 §1 的概念部分**保留 Anthropic SDK 详解**——这是后续 W3 tool use / content blocks / prompt caching 等高级主题的概念基础，不会白学。但 §3 实战会先用 Kimi 跑通主线，再 dump 一次 Anthropic 做对比。

---

## 1. 概念：anthropic SDK / Typer / service 层

### 1.1 anthropic SDK

#### 是什么
Anthropic 官方的 Python 客户端，封装了 HTTP 调用、鉴权、重试、流式响应等细节。最新版本（`0.100.x`+）同时提供同步和异步两套 API：

```python
from anthropic import Anthropic, AsyncAnthropic

client_sync  = Anthropic()                  # 同步：阻塞调用
client_async = AsyncAnthropic()             # 异步：必须 await
```

**夕拾必须用 `AsyncAnthropic`**——理由见 W1-D1 笔记的"async 三大陷阱 #2：同步调用混进 async 卡死全 loop"。

#### Messages API 核心调用形态

```python
response = await client.messages.create(
    model="claude-haiku-4-5",                # 模型 ID
    max_tokens=1024,                         # 必填，强制上限避免烧钱
    system="你是一个分类器...",                # 可选，系统提示
    messages=[
        {"role": "user", "content": "今天孩子又闹脾气了"},
        # 多轮对话就在这里追加 assistant 和 user 消息
    ],
)
```

**关键 5 个字段你必须能讲清楚**：

| 字段 | 含义 | 陷阱 |
|---|---|---|
| `model` | 模型 ID 字符串 | Sonnet 4.6 = `claude-sonnet-4-6`，Haiku 4.5 = `claude-haiku-4-5`，写错直接 404 |
| `max_tokens` | 输出 token 上限 | **必填**，防失控。Haiku 路由任务设 256 就够 |
| `system` | 系统提示 | 是字符串或 `list[dict]`（后者用于 prompt caching） |
| `messages` | 对话历史 | 必须 `user` 开头，`user/assistant` 交替；**SDK 不替你存历史**，你要自己维护 |
| `stop_sequences` | 命中即停 | 选项，用于 tool use 之前的简单约束 |

#### 响应对象结构

`response` 不是 dict 而是 Pydantic v2 model。**关键 4 个字段**（D3 实战里你会亲手 dump 出来确认）：

```python
response.id              # 这次调用的唯一 ID（str）
response.model           # 实际跑的模型（str）
response.stop_reason     # 为什么停的：'end_turn' | 'max_tokens' | 'stop_sequence' | 'tool_use'
response.usage           # token 用量：input_tokens / output_tokens / cache_*
response.content         # list[ContentBlock]，每个 block 有 type='text' 或 'tool_use' 等
```

**`response.content` 是 list 不是 str**——这是新手第一坑。要拿文本必须遍历：

```python
text = "".join(block.text for block in response.content if block.type == "text")
```

#### `stop_reason` 的 4 个值（W3 tool use 会重点用）

| 值 | 含义 | 此时该做什么 |
|---|---|---|
| `end_turn` | 模型自然说完 | 把响应给用户，结束 |
| `max_tokens` | 撞到上限被截断 | 提示用户或自动续写 |
| `stop_sequence` | 命中你设的 stop string | 拆解输出 |
| `tool_use` | 模型要调工具 | 进入 tool use 循环（W3 主题） |

### 1.1.5 Kimi K2 / OpenAI 兼容 SDK（主线实现走这条）

#### 为什么走 OpenAI 兼容协议

Kimi、DeepSeek、智谱 GLM、通义、阶跃、本地 vLLM 全部支持 OpenAI 兼容协议——**学一套 schema 通吃国产 + 本地全家桶**。这是夕拾主线选 Kimi 的核心理由（详见 [decisions.md#D19](../decisions.md)）。

#### 核心调用形态

```python
from openai import AsyncOpenAI

client = AsyncOpenAI(
    api_key=settings.kimi_api_key,
    base_url="https://api.moonshot.cn/v1",     # 这一行 = 切换 provider 的唯一钩子
)

response = await client.chat.completions.create(
    model="kimi-k2-0905-preview",              # Kimi K2 当前推荐 ID（写代码前先确认控制台）
    max_tokens=256,
    messages=[
        {"role": "system", "content": "你是一个分类器..."},
        {"role": "user",   "content": "今天孩子又闹脾气了"},
    ],
)
```

#### 与 Anthropic 的范式差异（面试拷问点，亲手 dump 才能记住）

| 维度 | OpenAI 兼容（Kimi/DS/...） | Anthropic |
|---|---|---|
| 拿文本 | `response.choices[0].message.content`（字符串） | `response.content[*].text`（block 列表，要遍历） |
| 多轮历史 | `messages` 数组里 system / user / assistant 平铺 | system 独立字段 + messages 只放 user/assistant |
| 工具调用 | `tool_calls` 字段（OpenAI 历史包袱：先 function_call 后改 tool_calls） | `tool_use` block 嵌在 content 里 |
| 停止原因 | `finish_reason`：`stop` / `length` / `tool_calls` | `stop_reason`：`end_turn` / `max_tokens` / `tool_use` |
| 用量 | `usage.prompt_tokens` / `completion_tokens` | `usage.input_tokens` / `output_tokens` |
| 思考过程 | Kimi 用 `reasoning_content`（非标准扩展） | `thinking` block（一等公民） |

**关键洞察**：Anthropic 的 content blocks 是**统一抽象**——text / tool_use / thinking 都是 block 类型。OpenAI 兼容协议是**字段拼贴**——text 在 message.content、tool 在 tool_calls、思考在 reasoning_content。前者更现代，后者更普及。理解这层差异，比"哪个更好"的口水仗有价值得多。

#### Kimi 当前可用模型（写代码前先去 platform.moonshot.cn 控制台确认）

- `kimi-k2-0905-preview`：K2 主力，agentic 任务推荐
- `moonshot-v1-8k` / `moonshot-v1-32k` / `moonshot-v1-128k`：旧 v1 系列，按 context 长度计费
- 路由分类用 K2 即可（Kimi 没有"Haiku 级"小模型，但 K2 的价格已经够低）

### 1.2 Typer

#### 是什么
**用 type hint 定义 CLI 子命令**的库，作者 tiangolo（FastAPI 同一人）。和 FastAPI 一脉相承的体验：函数签名即 schema。

```python
import typer
app = typer.Typer()

@app.command()
def ask(text: str, model: str = "haiku"):
    """问 Claude 一个问题。"""
    ...

if __name__ == "__main__":
    app()
```

跑起来后：

```bash
xishi ask "今天天气怎么样"           # text 是 positional
xishi ask "今天天气怎么样" --model sonnet  # model 是 option，type hint 决定
xishi ask --help                    # 自动生成的帮助
```

#### Typer vs Click（面试爱问）

| | Typer | Click |
|---|---|---|
| 风格 | type hint 驱动，函数签名即 spec | 装饰器手写 `@click.option(...)` |
| 类型校验 | 自动（基于注解） | 手动声明 `type=int` |
| 适合 | 现代 Python（3.9+） | 历史项目 / 兼容老 Python |
| 底层 | 基于 Click | 自身 |

Typer 选型理由：和 Pydantic / FastAPI 思想一致——**类型注解是 single source of truth**。

#### 一个关键陷阱：Typer 命令不能直接 `async def`

Typer 不知道怎么跑 coroutine。你写：

```python
@app.command()
async def ask(text: str):                   # ← 直接 async def 会出问题
    response = await client.messages.create(...)
```

跑起来 Typer 拿到一个 coroutine 对象就 print 了 `<coroutine object ...>` 然后退出——函数体根本没执行（**这就是 W1-D1 讲的 async 三大陷阱 #1：忘了 await**，Typer 帮你"忘"了）。

正确写法：用同步 wrapper 包一层 `asyncio.run`：

```python
import asyncio

@app.command()
def ask(text: str):
    asyncio.run(_ask_impl(text))            # 同步入口，内部启动 event loop

async def _ask_impl(text: str):
    response = await client.messages.create(...)
    ...
```

这是 Typer + async 项目的标准模式。理解了之后你会发现 FastAPI 路由能直接 `async def` 是因为 **uvicorn 已经替你跑了 event loop**——Typer 没这个待遇。

### 1.3 Service 层是什么 / 为什么要分层

**Service 层 = 领域逻辑的归属地**。它的边界：

- ✅ 接受**纯数据输入**，返回**纯数据输出**
- ✅ 跟入口（CLI / HTTP / cron）**完全无关**
- ❌ 不知道自己被谁调用
- ❌ 不写 `typer.echo` / `print` / HTTP 状态码
- ❌ 不读 `sys.argv` / `request.json`

```
xishi.cli       (Typer 命令，负责"接受用户输入 + 调 service + 格式化输出")
    ↓
xishi.service   (领域逻辑，纯函数化，async)
    ↓
xishi.adapters  (anthropic / postgres / 第三方 IO，后面才铺)
```

#### 为什么分层这么严格

**面试拷问点**：

1. **可测试**：service 是纯函数，单测不需要起 Typer / FastAPI
2. **复用**：M3 加 FastAPI 路由时**零改动 service**，路由只是新入口
3. **关注点分离**：CLI 关心"参数解析 + 输出格式"，service 关心"分类逻辑 + LLM 调用"
4. **未来异步装订**：cron 跑 `xishi bind` 也是另一个入口，照样调同一个 service

新手错误：把 anthropic 调用直接写在 Typer 命令体里。**那样写 = M3 加 HTTP 时整段复制粘贴**——违反 DRY，也证明分层意识没建立。

### 1.4 observe-before-implement（项目规则）

这是你 CLAUDE.md 的全局规则：**对接新 API 时，先用最小脚本 dump 真实响应结构，再写解析代码**。

D3 实战会让你写一个 `scripts/observe_anthropic.py`——它**不在主代码路径上**，但产物（dump 出的 JSON 结构）会贴进笔记。这一步省了，到 W2 写 service 解析时会被 `response.content[0].text` 还是 `response.content[0]["text"]` 这种细节坑住。

---

## 2. 自检题（Quiz）

每题先想答案，再展开 `<details>` 对照。**做不出来的题不要跳——回到上面对应章节重读**。

### Q1
`AsyncAnthropic` 和 `Anthropic` 的区别是什么？夕拾为什么必须用前者？

<details>
<summary>答案</summary>

- `Anthropic` = 同步客户端，`client.messages.create(...)` 直接返回 response，阻塞当前线程
- `AsyncAnthropic` = 异步客户端，`await client.messages.create(...)` 让出 event loop

夕拾必须用前者的理由：FastAPI / Typer 命令体里都跑在 event loop 上，混入同步阻塞调用 = 卡死整个 loop（W1-D1 async 陷阱 #2）。一次 LLM 调用 1-30 秒的阻塞是不可接受的。

</details>

### Q2
`response.content` 是什么类型？想拿到模型的纯文本回复要怎么做？为什么不直接 `response.content[0].text`？

<details>
<summary>答案</summary>

- 类型：`list[ContentBlock]`
- 每个 block 有 `type` 字段，可能是 `'text'` / `'tool_use'` / `'thinking'`（启用扩展思考时）等
- 拿文本要遍历过滤：

  ```python
  text = "".join(block.text for block in response.content if block.type == "text")
  ```

- 不能直接 `response.content[0].text` 的原因：当 stop_reason 是 `tool_use` 时第 0 个 block 可能是 `tool_use` 类型，没有 `.text` 属性，直接访问 AttributeError

</details>

### Q3
`stop_reason` 的 4 个值分别是什么？看到 `max_tokens` 时该怎么处理？

<details>
<summary>答案</summary>

- `end_turn`：模型自然结束 → 正常使用响应
- `max_tokens`：撞到 `max_tokens` 上限被截断 → 提示用户结果被截断，或自动续写（不推荐，会烧钱）
- `stop_sequence`：命中 `stop_sequences` 参数里设的字符串 → 按拆分逻辑处理
- `tool_use`：模型要调工具 → 进入 tool use 循环（W3 主题）

</details>

### Q4
为什么 Typer 命令不能直接 `async def`？正确写法是什么？

<details>
<summary>答案</summary>

Typer 调用命令函数时不会自动 `asyncio.run`——它拿到 coroutine 对象后只 print 一下就退出，函数体未执行（async 陷阱"忘了 await"）。

正确写法：

```python
@app.command()
def ask(text: str):
    asyncio.run(_ask_impl(text))

async def _ask_impl(text: str):
    ...
```

FastAPI 路由能直接 `async def` 是因为 uvicorn 已经替你跑了 event loop；Typer 没这个待遇。

</details>

### Q5
为什么 anthropic 调用要写在 `xishi.service.llm`，不能写在 Typer 命令体里？

<details>
<summary>答案</summary>

Service 层 = 领域逻辑归属，**跟入口完全无关**。理由：

1. 可测试：service 是纯函数，单测不需要起 Typer
2. 复用：M3 加 FastAPI 路由时零改动 service
3. 关注点分离：CLI 关心参数解析+输出格式，service 关心 LLM 调用本身
4. 异步装订（cron）和未来的 HTTP 都是新入口，共享同一个 service

写在 Typer 命令体里 = M3 加 HTTP 整段复制 = 违反 DRY，也是分层意识没建立的信号。

</details>

### Q6
为什么必须先 dump 一次真实响应再写解析代码？给一个具体可能踩的坑。

<details>
<summary>答案</summary>

observe-before-implement 规则：**避免基于猜测/文档写出与真实数据不符的代码**。

具体例子：你以为 `response.content` 是字符串，写出 `text = response.content.strip()`——跑起来 `AttributeError: 'list' object has no attribute 'strip'`。或者你以为 `usage.input_tokens` 是字段，实际可能是 `usage["input_tokens"]`（dict）——这种二选一的写法不 dump 一次永远会错一半。

</details>

### Q7
`max_tokens` 这个参数为什么是必填的？设多少合适？

<parameter>
<details>
<summary>答案</summary>

必填的原因：Anthropic API 强制要求，防止失控生成烧钱（早期 LLM 提供商常见血泪教训）。

设置建议：
- 路由分类任务（Haiku，输出 JSON 短字符串）：`256` 够用
- 装订手帐（Sonnet，生成几百字总结）：`2048`-`4096`
- 长创作：`8192`+

宁多勿少？不对——多了不会被收钱（只收实际生成的），但**给模型留太多 token 反而容易让它啰嗦**。

</details>

### Q8
如果同一段对话要连续调 2 次（用户先说一句、模型回一句、用户又说一句），第二次调用 `messages` 字段应该传什么？

<details>
<summary>答案</summary>

**整段历史全部重传**，包括第一次的 user 消息、assistant 响应、第二次的 user 消息：

```python
messages = [
    {"role": "user",      "content": "今天孩子又闹脾气了"},
    {"role": "assistant", "content": "听起来你很挫败..."},
    {"role": "user",      "content": "对，但我也不知道怎么做"},
]
```

**Anthropic API 是无状态的**——它不替你存对话历史，每次调用你都要自己维护并完整重传。这跟 ChatGPT 网页对话的"自动接上文"是两回事。

后续：prompt caching（W6 主题）就是用来让这种"每次都重传"的开销变低的。

</details>

---

## 3. 实战任务（Hands-on）

### 3.1 前置：拿到 Kimi + Anthropic 两把 key

**两个都要拿**——Kimi 是主线（成本低、跑得多），Anthropic 只为 §3.3 一次对比 dump。

#### Kimi（主线）

- 去 https://platform.moonshot.cn → API Keys → 新建
- 充值建议 ¥10（够跑几千次 K2 调用）
- 复制到 `.env`：

  ```
  KIMI_API_KEY=sk-真实key
  KIMI_BASE_URL=https://api.moonshot.cn/v1
  ```

#### Anthropic（仅 D3 对比用，可后置）

- 去 https://console.anthropic.com → API Keys → Create Key
- 充值建议 $5（D3 只用一次，剩下的留给 W3 tool use）
- 复制到 `.env`：

  ```
  ANTHROPIC_API_KEY=sk-ant-真实key
  ```

#### 同步更新 `config.py`

`Settings` 类需要新增 `kimi_api_key` 和 `kimi_base_url` 字段，同时把 `llm_configured` 改成判断 Kimi key（主线 provider）：

```python
class Settings(BaseSettings):
    kimi_api_key: str = ""
    kimi_base_url: str = "https://api.moonshot.cn/v1"
    anthropic_api_key: str = ""        # 仍保留，D3 对比用
    # ...

    @property
    def llm_configured(self) -> bool:
        return self.kimi_api_key.startswith("sk-") and len(self.kimi_api_key) > 20
```

`.env.example` 也要同步加上这两条占位（让 GitHub 公开仓库可被他人复现）。

### 3.2 安装依赖

```bash
uv add openai anthropic typer
```

两个 SDK 都要装：`openai` 是主线（接 Kimi），`anthropic` 仅 §3.3 对比用。

### 3.3 写 observe 脚本（双 provider dump，建立跨范式肌肉记忆）

新建两个脚本，**不进 src/**，只是观察工具：

#### 3.3.1 `scripts/observe_kimi.py`（主线）

任务：
- 用 `AsyncOpenAI` + Kimi base_url 调一次 K2
- prompt 用"用一句话介绍夕拾这个项目"或类似简短问题
- 把 `response.model_dump()` 完整打印
- 重点观察：
  - `choices[0].message.content` 的类型（字符串！）
  - `usage.prompt_tokens` / `completion_tokens` 字段名
  - `choices[0].finish_reason` 的值

<details>
<summary>参考骨架（先自己写，遇阻再看）</summary>

```python
"""一次性观察 Kimi（OpenAI 兼容）chat.completions API 的响应结构。"""
import asyncio
import json

from openai import AsyncOpenAI

from xishi.config import settings


async def main() -> None:
    client = AsyncOpenAI(
        api_key=settings.kimi_api_key,
        base_url=settings.kimi_base_url,
    )
    response = await client.chat.completions.create(
        model="kimi-k2-0905-preview",
        max_tokens=256,
        messages=[
            {"role": "user", "content": "用一句话介绍夕拾这个项目。"},
        ],
    )
    print(json.dumps(response.model_dump(), indent=2, ensure_ascii=False))


if __name__ == "__main__":
    asyncio.run(main())
```

跑：`uv run python scripts/observe_kimi.py`

</details>

#### 3.3.2 `scripts/observe_anthropic.py`（对比）

同样的 prompt，换 Anthropic 跑一次，看 response 结构差在哪。

<details>
<summary>参考骨架</summary>

```python
"""一次性观察 Anthropic Messages API 的响应结构，用于和 Kimi 对比。"""
import asyncio
import json

from anthropic import AsyncAnthropic

from xishi.config import settings


async def main() -> None:
    client = AsyncAnthropic(api_key=settings.anthropic_api_key)
    response = await client.messages.create(
        model="claude-haiku-4-5",
        max_tokens=256,
        messages=[
            {"role": "user", "content": "用一句话介绍夕拾这个项目。"},
        ],
    )
    print(json.dumps(response.model_dump(), indent=2, ensure_ascii=False))


if __name__ == "__main__":
    asyncio.run(main())
```

跑：`uv run python scripts/observe_anthropic.py`

</details>

#### 3.3.3 对比观察（笔记必填环节）

两份输出贴进 W1-D3 笔记后，**亲手填这张表**（写不出的格子回到 §1.1.5 对比表重读）：

| 我想拿到 | Kimi（OpenAI 兼容） | Anthropic |
|---|---|---|
| 模型回复的文本 | `response.choices[0].message.content` | `response.content[0].text`（且要先确认 type=='text'） |
| 输入 token 数 | `response.usage.prompt_tokens` | `response.usage.input_tokens` |
| 输出 token 数 | `response.usage.completion_tokens` | `response.usage.output_tokens` |
| 为啥停了 | `response.choices[0].finish_reason` | `response.stop_reason` |
| 本次调用 ID | `response.id` | `response.id` |

**这就是 observe-before-implement 规则的核心收益**——亲手 dump 一次比读十遍文档可靠。

### 3.4 创建 service 层

目录结构：

```
src/xishi/
├── __init__.py
├── config.py
├── main.py                    (FastAPI app，保留)
├── cli.py                     (新增：Typer app)
└── service/
    ├── __init__.py
    └── llm.py                 (新增：anthropic 封装)
```

`src/xishi/service/llm.py` 的职责：

- 提供一个 `async def ask(text: str, model: str = "kimi") -> str` 函数
- 内部维护单例 `AsyncOpenAI` 客户端（指向 Kimi base_url）
- 接受纯字符串输入，返回纯字符串响应文本
- **不打印、不格式化、不感知 CLI/HTTP**
- **不预先抽象 LLMClient 协议**（见 [decisions.md#D19](../decisions.md)"未做"条款）

模型别名映射建议：

```python
MODELS = {
    "kimi":  "kimi-k2-0905-preview",       # 主力，agentic 任务
    "kimi-long": "moonshot-v1-128k",        # 长 context 备选
}
```

> **为什么不预先把 anthropic 也接进来？** 违反"简洁优先"——D3 还没有"需要切 provider"的真实场景。等 W2 出现成本压力或需要回退能力时再加 `LLMClient` 协议（约 30 行抽象 + 两个 impl），那才是有理由的抽象。现在多写就是 YAGNI。

### 3.5 创建 Typer CLI

`src/xishi/cli.py`：

- 创建 `app = typer.Typer()`
- 定义 `ask` 命令：参数 `text: str` + option `model: str = "kimi"`
- 命令体内用 `asyncio.run(...)` 包 service 调用
- 用 `typer.echo()` 输出结果

`pyproject.toml` 注册入口（**这一步很关键**）：

```toml
[project.scripts]
xishi = "xishi.cli:app"
```

然后 `uv sync` 重新装包，之后 `uv run xishi ask "..."` 就能跑。

### 3.6 验证

```bash
uv run xishi ask "用一句话介绍夕拾这个项目"
# 应该输出 Kimi K2 的一句话答案

uv run xishi ask "解释 async/await" --model kimi-long
# 应该用 moonshot-v1-128k 跑出较详细的答案

uv run xishi --help
# 应该显示 ask 子命令的帮助
```

---

## 4. 验收标准（DoD）

打勾自检，全过才算 D3 完成：

- [ ] `uv add openai anthropic typer` 完成，`uv.lock` 已更新
- [ ] `.env` 里 `KIMI_API_KEY` 和 `ANTHROPIC_API_KEY` 都是真 key（不是占位）
- [ ] `.env.example` 同步加上 `KIMI_API_KEY` / `KIMI_BASE_URL` 占位
- [ ] `config.py` 加上 `kimi_api_key` / `kimi_base_url` 字段，`llm_configured` 改为判断 Kimi key
- [ ] `scripts/observe_kimi.py` 写完且跑通，输出贴进 D3 笔记
- [ ] `scripts/observe_anthropic.py` 写完且跑通，输出贴进 D3 笔记
- [ ] D3 笔记里有 §3.3.3 的**跨 provider 对比表**（亲手填，不抄）
- [ ] `src/xishi/service/llm.py` 存在，`ask()` 是 `async def`，用 `AsyncOpenAI` + Kimi base_url，且不感知 CLI
- [ ] `src/xishi/cli.py` 存在，`ask` 命令用 `asyncio.run` 包装
- [ ] `pyproject.toml` 的 `[project.scripts]` 注册了 `xishi`
- [ ] `uv run xishi ask "..."` 三个测试全部跑通（kimi / kimi-long / --help）
- [ ] D3 commit 干净（建议拆 3-4 个：config 扩展 / observe 脚本 / service 层 / cli 入口）
- [ ] `docs/notes/W1-D3.md` 写完，至少包含：今日产出 / 概念巩固（Kimi-OpenAI 兼容 / anthropic SDK / Typer / service 层）/ 两份 observe 输出片段 / 跨 provider 对比表 / 卡点 / D4 预告

---

## 5. 笔记模板（Notes scaffold）

不强制按这个写，但建议保持和 D1 笔记一致的结构。新建 `docs/notes/W1-D3.md`：

```markdown
# W1-D3 学习笔记

**日期**：2026-05-11
**主题**：anthropic SDK + Typer CLI + service 层雏形
**用时**：约 Xh

---

## 今日产出
- [ ] ...

## 概念巩固

### 一、anthropic SDK
#### 核心
- ...
#### 关键字段（messages.create 参数）
- ...
#### 响应结构（observe 脚本验证）
```json
{
  "id": "...",
  "stop_reason": "...",
  ...
}
```
#### 面试拷问准备
- ...

### 二、Typer
- ...

### 三、service 层 / 分层架构
- ...

## 卡点
- ...

## D4 预告
- 写 zone 分类 prompt（首版："灵感 / 亲子 / 心情"三选一 + confidence）
- 用 JSON 输出模式（system prompt 约束 + response_format）
- 升级 `xishi ask` 为 `xishi route`
```

---

## 6. D4 预告（看个目标就行，明天再讲）

D4 主题：**用 Haiku 做 zone 分类**。

- 写 zone 分类的 system prompt（含 few-shot 示例）
- 约束 Haiku 输出 JSON：`{"zone": "...", "confidence": 0.x, "reasoning": "..."}`
- 把 `xishi ask` 改名 `xishi route`，service 层加 `classify(text) -> ZoneClassification` 函数（Pydantic model 接住 JSON）
- 100 行 demo 接近完成

---

完成 D3 后，把 commit 推上来，明天 D4 教案见。
