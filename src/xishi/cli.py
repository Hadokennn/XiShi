"""夕拾 CLI 入口。

职责严格限定：
- 解析命令行参数
- 调用 service 层
- 格式化输出（typer.echo）

不做：业务逻辑、LLM 调用、DB 访问——那些归 service。
"""
from __future__ import annotations

import asyncio

import typer

from xishi.service.llm import ask as svc_ask

app = typer.Typer(help="夕拾（Xishi）CLI——手帐式第二大脑")

@app.command()
def ask(
    text: str = typer.Argument(..., help="要问的问题"),
    model: str = typer.Option("ds", "--model", "-m", help="模型别名：kimi / kimi-long / ds"),
) -> None:
    """问 LLM 一个问题，打印回复。"""
    answer = asyncio.run(svc_ask(text, model=model))
    typer.echo(answer)
