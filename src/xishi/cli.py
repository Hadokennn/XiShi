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
from xishi.service.route import RouteParseError
from xishi.service.route import route as svc_route

app = typer.Typer(help="夕拾（Xishi）CLI——手帐式第二大脑")

_ZONE_LABEL = {
    "inspiration": "灵感",
    "parenting": "亲子",
    "mood": "心情",
}


@app.command()
def ask(
    text: str = typer.Argument(..., help="要问的问题"),
    model: str = typer.Option("ds", "--model", "-m", help="模型别名：kimi / kimi-long / ds"),
) -> None:
    """问 LLM 一个问题，打印回复。"""
    answer = asyncio.run(svc_ask(text, model=model))
    typer.echo(answer)


@app.command()
def route(
    text: str = typer.Argument(..., help="要分区的一段话"),
    model: str = typer.Option("kimi", "--model", "-m", help="模型别名：kimi / kimi-long / ds"),
) -> None:
    """把一段话路由到夕拾的三个分区之一（或多个）。"""
    try:
        result = asyncio.run(svc_route(text, model=model))
    except RouteParseError as e:
        typer.echo(f"❌ 路由失败：{e.last_error}", err=True)
        typer.echo(f"\n第一次 raw：{e.raw_first}", err=True)
        typer.echo(f"第二次 raw：{e.raw_second}", err=True)
        raise typer.Exit(code=1)

    primary = result.primary_zone_id
    primary_conf = result.zone_confidence[primary]
    typer.echo(
        f"► {primary} ({_ZONE_LABEL[primary]} · 主) · {primary_conf:.2f}"
    )
    for z in result.zone_ids:
        if z == primary:
            continue
        typer.echo(f"  {z} ({_ZONE_LABEL[z]}) · {result.zone_confidence[z]:.2f}")
    # 显示模型给的软标注（zone_ids 之外但 confidence 不为 0 的）
    extras = [
        (z, c)
        for z, c in result.zone_confidence.items()
        if z not in result.zone_ids
    ]
    for z, c in extras:
        typer.echo(f"  · {z} ({_ZONE_LABEL[z]}) · {c:.2f}（软标注）")
    typer.echo(f"  💭 {result.reasoning}")
