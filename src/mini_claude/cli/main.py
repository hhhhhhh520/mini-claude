"""Main CLI entry point."""

import asyncio
from typing import Optional

import click
from dotenv import load_dotenv
from rich.panel import Panel

from .display import display
from .repl import REPLSession


def load_environment():
    """Load environment variables."""
    load_dotenv()


def _suppress_third_party_stdout_noise():
    """P0-3：第三方库（litellm）出错时往 stdout 打广告，污染 --json。

    Best-effort：litellm 未装也不炸；正常人类输出不受影响。
    """
    import os

    os.environ.setdefault("LITELLM_LOG", "ERROR")
    # 不设此项时 litellm 启动会去 GitHub 拉远程 model cost map，
    # 网络不通/SSL 失败要空等约 8 秒（本机实测）才回退本地副本。
    # 关掉不影响功能：成本表本就有随包本地副本。
    os.environ.setdefault("LITELLM_LOCAL_MODEL_COST_MAP", "True")
    try:
        import litellm

        litellm.suppress_debug_info = True
    except ImportError:
        pass


def init_logging():
    """Initialize logging system."""
    from ..utils.logger import init_logging_from_settings

    init_logging_from_settings()


@click.group(invoke_without_command=True)
@click.option("--model", "-m", default=None, help="Model to use")
@click.option("--workspace", "-w", default=None, help="Workspace directory")
@click.option("--debug", is_flag=True, help="Enable debug mode")
@click.pass_context
def main(ctx, model: Optional[str], workspace: str, debug: bool):
    """Mini Claude Code - A multi-agent CLI assistant."""
    load_environment()
    _suppress_third_party_stdout_noise()
    if debug:
        # ISSUE-017：--debug 不再是死参数——它把日志级别提到 DEBUG
        # （与 repl 里写 settings.workspace_root 同构；init_logging 之前生效）。
        from mini_claude.config.settings import settings

        settings.log_level = "DEBUG"
    init_logging()
    ctx.ensure_object(dict)
    ctx.obj["model"] = model
    ctx.obj["workspace"] = workspace
    ctx.obj["debug"] = debug

    # If no subcommand, enter REPL mode
    if ctx.invoked_subcommand is None:
        ctx.invoke(repl)


@main.command()
@click.pass_context
def repl(ctx):
    """Start interactive REPL mode."""
    from mini_claude.config.settings import settings
    import os

    # Update workspace from context (use settings default if not specified)
    workspace = ctx.obj.get("workspace")
    if workspace:
        settings.workspace_root = os.path.abspath(workspace)

    # Show workspace info
    display.console.print(f"[dim]Workspace: {settings.workspace_root}[/]")

    # Start REPL session
    session = REPLSession()
    session.initialize()

    try:
        asyncio.run(session.run_graph())  # 使用 LangGraph 状态机
    except KeyboardInterrupt:
        display.console.print("\n[dim]Goodbye![/]")


@main.command()
@click.argument("prompt")
@click.option("--model", "-m", default=None, help="Model to use")
@click.option("--json", "output_json", is_flag=True, help="Output as JSON")
@click.option(
    "--full",
    is_flag=True,
    help="P1-6：走完整 LangGraph 主循环（多步工具/恢复），默认只做快捷两步问答。",
)
@click.pass_context
def ask(ctx, prompt: str, model: Optional[str], output_json: bool, full: bool):
    """Execute a single prompt and exit.

    默认 ask 是快捷两步（问答+一批工具+汇总），便宜快速；
    REPL 是完整主循环（THINK→PLAN→ACT→OBSERVE→CHECK，多轮/恢复）。
    要单条命令走完整循环用 --full（慢、贵，但能多步）。
    """
    import json
    import traceback
    from ..llm.provider import LLMProvider, convert_tools_to_litellm
    from ..tools import get_all_tools, execute_tool
    from ..utils.logger import get_logger

    logger = get_logger(__name__)
    debug = bool((ctx.obj or {}).get("debug"))

    load_environment()

    def _error_payload(e: Exception) -> dict:
        # P1-7：错误原文保留给脚本，中文 hint 给人看（复用 health 分类器）。
        payload = {"error": str(e)}
        try:
            from ..monitoring.health import classify_model_error

            hint = classify_model_error(str(e))
            if hint:
                payload["hint"] = hint
        except Exception:
            pass
        return payload

    def _show_error(e: Exception) -> None:
        display.show_error(str(e))
        try:
            from rich.markup import escape

            from ..monitoring.health import classify_model_error

            hint = classify_model_error(str(e))
            if hint:
                # 分类器当前恒返常量，但别把 markup 注入面留给未来的改动。
                display.console.print(f"[yellow]下一步：{escape(hint)}[/]")
        except Exception:
            pass

    async def _cleanup_background() -> None:
        from ..tools._http import close_shared_client
        from ..tools.bash import (
            cleanup_all_background_processes,
            get_background_process_count,
        )

        if get_background_process_count() > 0:
            if not output_json:
                display.console.print("[dim]清理后台进程...[/]")
            await cleanup_all_background_processes()
        # 共享 httpx client（web 工具）连接收口——与后台进程/checkpoint 同级纪律
        await close_shared_client()

    async def run_full():
        """P1-6：完整主循环单发版（无 checkpoint，不污染 REPL 会话）."""
        import contextlib
        import sys as _sys

        from ..agent.graph import build_agent_graph_no_checkpoint
        from ..agent.state import create_initial_state

        if not output_json:
            display.user_message(prompt)
            display.show_thinking()

        # MCP 自动连接（P2）：配置了 mcp.json 就连接，单命令模式也能用远端工具；
        # 失败只提示不阻断。--json 下提示必须走 stderr（stdout 只留最终 JSON 一行）
        try:
            from ..mcp.manager import auto_connect_on_startup

            _out = (
                contextlib.redirect_stdout(_sys.stderr) if output_json else contextlib.nullcontext()
            )
            with _out:
                connected, errors = await auto_connect_on_startup()
                for name, err in errors.items():
                    display.console.print(f"[yellow]MCP server {name} 连接失败：{err}[/]")
                if connected:
                    display.console.print(f"[dim]MCP 已连接: {', '.join(connected)}[/]")
        except Exception as e:
            display.show_error(f"MCP 自动连接失败：{e}")

        graph = build_agent_graph_no_checkpoint()
        try:
            # --json 下图节点里的 display（工具调用/流式）会直打 stdout，
            # 把整段图执行重定向到 stderr，stdout 只留最后的 JSON 一行。
            if output_json:
                with contextlib.redirect_stdout(_sys.stderr):
                    result = await graph.ainvoke(
                        create_initial_state(prompt, []),
                        {"recursion_limit": 50},
                    )
            else:
                result = await graph.ainvoke(
                    create_initial_state(prompt, []),
                    {"recursion_limit": 50},
                )
            messages = result.get("messages", [])
            last = messages[-1] if messages else None
            result_text = getattr(last, "content", "") if last is not None else ""
            result_text = result_text or ""
            if not output_json:
                display.agent_message(result_text)
            return result_text
        except Exception as e:
            logger.error(f"ask --full failed: {e}", exc_info=True)
            if debug:
                traceback.print_exc()
            if output_json:
                print(json.dumps(_error_payload(e), ensure_ascii=False))
            else:
                _show_error(e)
            raise SystemExit(1)
        finally:
            # SessionEnd hook：ask 会话收尾（资源清理前触发）
            try:
                from ..hooks.dispatcher import get_hook_dispatcher

                await get_hook_dispatcher().dispatch_session_end(reason="exit", thread_id="ask")
            except Exception as se_err:
                logger.debug("session end hook failed", error=str(se_err))
            await _cleanup_background()

    async def run_single():
        llm = LLMProvider(model)

        # SessionStart hook（P5 尾部事件）：ask 的一次执行即一个会话，
        # 与 REPL 同语义——非阻断，stdout/additionalContext 并入本次上下文
        start_context = ""
        try:
            from ..hooks.dispatcher import get_hook_dispatcher

            _, _, start_context = await get_hook_dispatcher().dispatch_session_start(
                source="startup", thread_id="ask"
            )
        except Exception as ss_err:
            logger.debug("session start hook failed", error=str(ss_err))

        # UserPromptSubmit hook（P5）：与 REPL 同语义——阻断则失败退出，
        # 注入上下文作为本次请求的 system 前缀。置于 display 之前：
        # 被拦截的输入不应显示"Thinking..."
        try:
            from ..hooks.dispatcher import get_hook_dispatcher

            (
                up_blocked,
                up_reason,
                up_context,
            ) = await get_hook_dispatcher().dispatch_user_prompt_submit(prompt, thread_id="ask")
        except Exception as up_err:
            logger.debug("user prompt submit hook failed", error=str(up_err))
            up_blocked, up_reason, up_context = False, "", ""
        if up_blocked:
            # 直接打印而非 _show_error：hook 拦截不是模型故障，
            # _show_error 会附带误导性的"模型调用失败"下一步提示
            err = f"输入被 UserPromptSubmit hook 拦截：{up_reason}"
            if output_json:
                print(json.dumps({"error": err}, ensure_ascii=False))
            else:
                print(f"Error: {err}")
            raise SystemExit(1)

        if not output_json:
            display.user_message(prompt)
            display.show_thinking()

        # Get tools
        tools = get_all_tools()
        litellm_tools = convert_tools_to_litellm(tools)

        messages = [{"role": "user", "content": prompt}]
        hook_context = "\n\n".join(part for part in (start_context, up_context) if part)
        if hook_context:
            messages.insert(
                0,
                {
                    "role": "system",
                    "content": f"以下内容来自 hooks（仅本次有效）：\n\n{hook_context}",
                },
            )

        try:
            # ISSUE-026：完整函数调用循环——assistant 消息原样携带 tool_calls、
            # 工具结果以 role=tool + tool_call_id 回传、后续调用继续带 tools。
            # 旧实现剥 tool_calls + user 文本回传，Qwen 类网关第二轮起丢失
            # 函数调用状态，把 <tool_call> 原生文本当正文输出。
            max_tool_rounds = 10
            rounds = 0
            result_text = ""
            while True:
                response = await llm.chat(
                    messages=messages,
                    tools=litellm_tools,
                    tool_choice="auto",
                )
                message = response.choices[0].message
                tool_calls = getattr(message, "tool_calls", None)
                if not tool_calls:
                    result_text = message.content or ""
                    break

                rounds += 1
                if rounds > max_tool_rounds:
                    result_text = (message.content or "") + "\n（工具调用轮数达到上限，已停止执行）"
                    break

                messages.append(
                    {
                        "role": "assistant",
                        "content": message.content or "",
                        "tool_calls": [
                            {
                                "id": tc.id,
                                "type": "function",
                                "function": {
                                    "name": tc.function.name,
                                    "arguments": tc.function.arguments,
                                },
                            }
                            for tc in tool_calls
                        ],
                    }
                )

                for tc in tool_calls:
                    tool_name = tc.function.name
                    tool_args = tc.function.arguments

                    if isinstance(tool_args, str):
                        try:
                            tool_args = json.loads(tool_args)
                        except json.JSONDecodeError as e:
                            logger.warning(
                                f"ask: tool arguments JSON parse failed ({e})",
                                tool_name=tool_name,
                            )
                            tool_args = {"_raw": str(tool_args)[:500]}

                    if not output_json:
                        print(f"[Tool] {tool_name}({tool_args})")
                    result = await execute_tool(tool_name, tool_args)

                    messages.append({"role": "tool", "tool_call_id": tc.id, "content": result})

            if not output_json:
                display.agent_message(result_text)
            return result_text
        except Exception as e:
            # ISSUE-020：堆栈不再丢弃——记进日志；--debug 下再打到终端。
            logger.error(f"ask failed: {e}", exc_info=True)
            if debug:
                traceback.print_exc()
            if output_json:
                print(json.dumps(_error_payload(e), ensure_ascii=False))
            else:
                _show_error(e)
            # 失败必须反映到退出码：脚本与 CI 只认退出码，
            # 只打印错误再正常返回会让它们把失败当成成功。
            raise SystemExit(1)
        finally:
            # ISSUE-018：ask 退出前清理后台进程（与 repl.run_graph 的 finally 同构）。
            # SystemExit 会穿过 finally，退出码语义不变；清理在事件循环内直接 await。
            await _cleanup_background()

    result_text = asyncio.run(run_full() if full else run_single())
    # ISSUE-017：--json 不再是死参数——只输出最终 JSON 一行，便于脚本解析。
    if output_json:
        print(json.dumps({"answer": result_text}, ensure_ascii=False))


@main.command()
@click.pass_context
def status(ctx):
    """Show current status."""
    from mini_claude.config.settings import settings

    display.console.print(
        Panel.fit(
            f"[bold]Model:[/] {settings.default_model}\n"
            f"[bold]Workspace:[/] {settings.workspace_root}\n"
            f"[bold]Max Sub-Agents:[/] {settings.max_sub_agents}\n"
            f"[bold]Max Iterations:[/] {settings.max_iterations}",
            title="Status",
        )
    )


@main.command()
@click.argument("model", required=False)
@click.pass_context
def model(ctx, model: str):
    """Show model info (switching via CLI is not supported).

    P0-5：此前打印 "Model set to: x" 实则什么都没改，是撒谎。
    与 REPL /model 对齐：只读展示 + 指到 .env。
    """
    from mini_claude.config.settings import settings

    display.console.print(f"[bold]当前模型:[/] {settings.default_model}")
    if model:
        display.console.print(
            f"[yellow]未切换到 {model}：CLI 动态切换未支持（provider/key/token 联动复杂）。[/]"
        )
    display.console.print("[dim]改模型请改 .env 的 DEFAULT_MODEL=... 后重跑[/]")


@main.command()
@click.option("--port", "-p", default=8080, help="Health server port")
@click.option("--json", "output_json", is_flag=True, help="Output as JSON")
@click.pass_context
def health(ctx, port: int, output_json: bool):
    """Check system health or start health server.

    Without --json flag: prints health status to console.
    With --json flag: outputs JSON to stdout.

    Use --port to specify a different port for the health server.
    """
    import asyncio
    from mini_claude.monitoring.health import check_health

    async def run_check():
        report = await check_health()

        if output_json:
            print(report.to_json())
        else:
            # Rich display
            from rich.panel import Panel

            # Service status
            display.console.print(
                Panel.fit(
                    f"[bold]Status:[/] {report.service.status.value}\n"
                    f"[bold]Uptime:[/] {report.service.to_dict()['uptime_human']}\n"
                    f"[bold]Memory:[/] {report.service.memory_usage_mb:.1f} MB\n"
                    f"[bold]CPU:[/] {report.service.cpu_percent:.1f}%",
                    title="Service",
                )
            )

            # Model status
            model_status_color = "green" if report.model.status == HealthStatus.HEALTHY else "red"
            display.console.print(
                Panel.fit(
                    f"[bold]Status:[/] [{model_status_color}]{report.model.status.value}[/{model_status_color}]\n"
                    f"[bold]Model:[/] {report.model.model_name}\n"
                    f"[bold]Provider:[/] {report.model.provider}"
                    + (
                        f"\n[bold]Response Time:[/] {report.model.response_time_ms:.0f}ms"
                        if report.model.response_time_ms
                        else ""
                    )
                    + (
                        f"\n[bold]Error:[/] {report.model.error_message}"
                        if report.model.error_message
                        else ""
                    ),
                    title="Model",
                )
            )

            # Tools status
            display.console.print(
                Panel.fit(
                    f"[bold]Status:[/] {report.tools.status.value}\n"
                    f"[bold]Available:[/] {report.tools.available_tools}/{report.tools.total_tools}\n"
                    f"[bold]Tools:[/] {', '.join(report.tools.tool_names[:5])}"
                    + (
                        f" (+{len(report.tools.tool_names) - 5} more)"
                        if len(report.tools.tool_names) > 5
                        else ""
                    ),
                    title="Tools",
                )
            )

            # Overall status
            overall_color = (
                "green"
                if report.overall_status() == HealthStatus.HEALTHY
                else "yellow"
                if report.overall_status() == HealthStatus.DEGRADED
                else "red"
            )
            display.console.print(
                f"\n[bold]Overall Status:[/] [{overall_color}]{report.overall_status().value}[/{overall_color}]"
            )

            # P0-2：本地没坏、只是模型钥匙/余额问题时必须明说，
            # 否则新人会把 402 当成安装失败。
            hint = report.model.action_hint()
            if hint:
                from rich.markup import escape

                if (
                    report.service.status == HealthStatus.HEALTHY
                    and report.tools.status == HealthStatus.HEALTHY
                ):
                    display.console.print(
                        "[yellow]本地服务与工具正常，只是模型调不通，装得没问题。[/]"
                    )
                display.console.print(f"[yellow]下一步：{escape(hint)}[/]")
                display.console.print("[dim]详查跑 mini-claude doctor[/]")

        return report

    # Import HealthStatus for display
    from mini_claude.monitoring.health import HealthStatus

    report = asyncio.run(run_check())

    # 与 health_handler 的 200/503 约定保持一致：非 HEALTHY 即失败。
    # 否则脚本/CI 拿到 unhealthy 的退出码 0，会当成系统正常。
    if report.overall_status() != HealthStatus.HEALTHY:
        raise SystemExit(1)


@main.command()
@click.pass_context
def doctor(ctx):
    """P0-2：新人自查钥匙/网络/工作区，不打真 LLM，不花钱。

    只查 presence（key 是否填了），绝不打印 key 明文。
    诊断命令永远 exit 0，问题看面板逐项修。
    """
    import os
    from pathlib import Path
    from rich.panel import Panel
    from rich.table import Table

    from mini_claude.config.settings import settings

    rows = []

    def _present(value) -> bool:
        return bool(value and str(value).strip())

    # 1. 模型与钥匙（只判有无）
    provider = settings.get_model_provider()
    rows.append(("默认模型", settings.default_model, True))
    rows.append(("Provider", str(getattr(provider, "value", provider)), True))
    has_key = any(
        [
            _present(settings.openai_api_key),
            _present(settings.anthropic_api_key),
            _present(settings.google_api_key),
        ]
    )
    rows.append(("API Key 已填", "是" if has_key else "否（.env 里填一个）", has_key))
    rows.append(
        ("Base URL", settings.openai_base_url or "默认官方", True),
    )

    # 2. 工作区与会话库
    ws = Path(settings.workspace_root)
    ws_ok = ws.exists()
    rows.append(("工作区存在", str(ws) if ws_ok else f"{ws} 不存在", ws_ok))
    try:
        writable = ws.exists() and os.access(ws, os.W_OK)
    except Exception:
        writable = False
    rows.append(("工作区可写", "是" if writable else "否", writable))
    try:
        db_parent = Path(settings.session_db_path).parent
        db_parent.mkdir(parents=True, exist_ok=True)
        rows.append(("会话库目录可写", str(db_parent), True))
    except Exception as e:
        rows.append(("会话库目录可写", f"否：{type(e).__name__}", False))

    # 3. 工具与可选依赖（只判 import，不跑网络）
    from mini_claude.tools import tool_registry

    tools = tool_registry.list_tools()
    rows.append(
        (
            f"工具注册 {len(tools)} 个",
            ", ".join(tools[:5]) + ("…" if len(tools) > 5 else ""),
            len(tools) > 0,
        )
    )

    def _has(mod: str) -> bool:
        try:
            __import__(mod)
            return True
        except ImportError:
            return False

    rows.append(("搜索依赖 ddgs", "已装" if _has("ddgs") else "未装→ pip install -e .[web]", True))
    rows.append(
        (
            "追踪依赖 otel",
            "已装" if _has("opentelemetry.trace") else "未装→ pip install -e .[tracing]",
            True,
        )
    )
    rows.append(
        ("服务依赖 aiohttp", "已装" if _has("aiohttp") else "未装→ pip install -e .[server]", True)
    )
    rows.append(
        (
            "向量依赖",
            "已装(chromadb/faiss)"
            if (_has("chromadb") or _has("faiss"))
            else "未装→ pip install -e .[vector]（可选）",
            True,
        )
    )

    table = Table(title="Doctor")
    table.add_column("检查项", style="cyan")
    table.add_column("结果", style="green")
    table.add_column("状态", style="bold")
    for name, result, ok in rows:
        table.add_row(name, str(result), "[green]OK[/]" if ok else "[red]修[/]")
    display.console.print(table)
    display.console.print(
        Panel.fit(
            "下一步：\n"
            "1. Key 没填 → 复制 .env.example 为 .env 填一个\n"
            "2. 欠费/401 → 按 health 的 action_hint 修\n"
            "3. 工作区不对 → mini-claude --workspace <dir> status",
            title="Next",
        )
    )


@main.command()
@click.option("--port", "-p", default=8080, help="Health server port")
@click.pass_context
def serve_health(ctx, port: int):
    """Start health check HTTP server.

    Provides endpoints:
    - /health - Full health check
    - /ready - Readiness probe (Kubernetes)
    - /live - Liveness probe (Kubernetes)
    """
    import asyncio
    from mini_claude.monitoring.health import run_health_server

    display.console.print(f"[dim]Starting health server on port {port}...[/]")
    try:
        asyncio.run(run_health_server(port=port, run=True))
    except RuntimeError as e:
        # P0-1：缺 aiohttp 时给安装指引，不打 traceback。
        display.show_error(str(e))
        raise SystemExit(1)


@main.command()
@click.option("--json", "output_json", is_flag=True, help="Output as JSON")
@click.pass_context
def metrics(ctx, output_json: bool):
    """Show Prometheus metrics.

    Displays all collected metrics including:
    - Request counts (total, success, failed)
    - Request latency distribution
    - Token usage
    - Tool call statistics
    """
    from mini_claude.monitoring.metrics import get_metrics, get_metrics_summary
    from rich.table import Table
    from rich.panel import Panel

    if output_json:
        # Output raw Prometheus format
        print(get_metrics())
    else:
        # Display human-readable summary
        summary = get_metrics_summary()

        # Requests table
        requests_table = Table(title="Request Metrics")
        requests_table.add_column("Metric", style="cyan")
        requests_table.add_column("Value", style="green")

        requests = summary["requests"]
        requests_table.add_row("Total", str(requests["total"]))
        requests_table.add_row("Success", str(requests["success"]))
        requests_table.add_row("Failed", str(requests["failed"]))
        requests_table.add_row("Active", str(requests["active"]))
        requests_table.add_row("Success Rate", f"{requests['success_rate']:.1f}%")

        display.console.print(requests_table)

        # Tokens table
        tokens_table = Table(title="Token Usage")
        tokens_table.add_column("Type", style="cyan")
        tokens_table.add_column("Count", style="green")

        tokens = summary["tokens"]
        tokens_table.add_row("Input", str(tokens["input"]))
        tokens_table.add_row("Output", str(tokens["output"]))
        tokens_table.add_row("Total", str(tokens["total"]))

        display.console.print(tokens_table)

        # Tools table
        tools_table = Table(title="Tool Calls")
        tools_table.add_column("Tool", style="cyan")
        tools_table.add_column("Success", style="green")
        tools_table.add_column("Failure", style="red")

        tools = summary["tools"]
        all_tools = set(tools["success"].keys()) | set(tools["failure"].keys())
        for tool_name in sorted(all_tools):
            success_count = tools["success"].get(tool_name, 0)
            failure_count = tools["failure"].get(tool_name, 0)
            tools_table.add_row(tool_name, str(success_count), str(failure_count))

        if all_tools:
            display.console.print(tools_table)
        else:
            display.console.print("[dim]No tool calls recorded[/]")

        # Performance
        perf = summary["performance"]
        display.console.print(
            Panel.fit(
                f"[bold]Avg Duration:[/] {perf['avg_duration_seconds']}s\n"
                f"[bold]Total Duration:[/] {perf['total_duration_seconds']}s\n"
                f"[bold]Uptime:[/] {summary['uptime_seconds']:.1f}s",
                title="Performance",
            )
        )


@main.command()
@click.option("--port", "-p", default=9090, help="Metrics server port (default: 9090)")
@click.pass_context
def serve_metrics(ctx, port: int):
    """Start Prometheus metrics HTTP server.

    Exposes /metrics endpoint for Prometheus scraping.
    Default port is 9090 (Prometheus convention).
    """
    from mini_claude.monitoring.metrics import run_metrics_server_sync

    display.console.print(f"[dim]Starting Prometheus metrics server on port {port}...[/]")
    display.console.print(f"[dim]Metrics available at http://localhost:{port}/metrics[/]")
    run_metrics_server_sync(port=port)


@main.command()
@click.argument("tool_name", required=False)
@click.option("--json", "output_json", is_flag=True, help="Output as JSON")
@click.pass_context
def tool_deps(ctx, tool_name: Optional[str], output_json: bool):
    """Show tool dependency graph.

    Without tool_name: shows the entire dependency graph.
    With tool_name: shows dependencies for that specific tool.

    Examples:
        mini-claude tool-deps              # Show all dependencies
        mini-claude tool-deps edit_file    # Show edit_file dependencies
        mini-claude tool-deps --json       # JSON output
    """
    from mini_claude.tools import tool_registry, get_dependency_graph
    from rich.table import Table
    from rich.panel import Panel
    from rich.tree import Tree
    import json

    graph = get_dependency_graph()

    # ISSUE-021：存在性检查必须在 --json 分支之前——原来 --json 先调
    # get_dependency_info，不存在的工具直接抛未捕获 ValueError。
    if tool_name and not tool_registry.get(tool_name):
        if output_json:
            print(json.dumps({"error": f"Tool '{tool_name}' not found"}))
        else:
            display.console.print(f"[red]Error: Tool '{tool_name}' not found[/]")
        raise SystemExit(1)

    if output_json:
        if tool_name:
            info = tool_registry.get_dependency_info(tool_name)
        else:
            info = graph.to_dict()
        print(json.dumps(info, indent=2))
        return

    if tool_name:
        # Show specific tool dependencies
        tool = tool_registry.get(tool_name)
        if not tool:
            display.console.print(f"[red]Error: Tool '{tool_name}' not found[/]")
            raise SystemExit(1)

        info = tool_registry.get_dependency_info(tool_name)
        available, missing_required, missing_optional = info["available"]

        # Dependencies panel
        deps_text = ""
        if info["dependencies"]:
            deps_text = "\n".join(f"  - {d}" for d in info["dependencies"])
        else:
            deps_text = "  (no direct dependencies)"

        # Dependents panel
        dependents_text = ""
        if info["dependents"]:
            dependents_text = "\n".join(f"  - {d}" for d in info["dependents"])
        else:
            dependents_text = "  (no dependents)"

        # All dependencies (transitive)
        all_deps_text = ""
        if info["all_dependencies"]:
            all_deps_text = "\n".join(f"  - {d}" for d in sorted(info["all_dependencies"]))
        else:
            all_deps_text = "  (no transitive dependencies)"

        display.console.print(
            Panel.fit(
                f"[bold]Direct Dependencies:[/]\n{deps_text}\n\n"
                f"[bold]All Dependencies (transitive):[/]\n{all_deps_text}\n\n"
                f"[bold]Dependents:[/]\n{dependents_text}",
                title=f"Tool: {tool_name}",
            )
        )

        # Availability status
        if available:
            display.console.print("[green]All required dependencies available[/]")
        else:
            display.console.print(f"[red]Missing required: {missing_required}[/]")

        if missing_optional:
            display.console.print(f"[yellow]Missing optional: {missing_optional}[/]")

    else:
        # Show entire dependency graph
        display.console.print(
            Panel.fit(
                f"[bold]Total Tools with Dependencies:[/] {len(graph._dependencies)}\n"
                f"[bold]Registered Tools:[/] {len(tool_registry._tools)}",
                title="Tool Dependency Graph",
            )
        )

        # Build tree visualization
        tree = Tree("[bold]Dependencies[/]")

        for tool, deps in sorted(graph._dependencies.items()):
            tool_node = tree.add(f"[cyan]{tool}[/]")
            for dep in deps:
                for d in dep.depends_on:
                    status = (
                        "[green]available[/]" if d in tool_registry._tools else "[red]missing[/]"
                    )
                    optional_marker = "[dim](optional)[/]" if dep.optional else ""
                    tool_node.add(f"{d} [{status}] {optional_marker}")

        display.console.print(tree)

        # Show dependents
        display.console.print("\n[bold]Dependents (reverse view):[/]")
        dependents_table = Table()
        dependents_table.add_column("Tool", style="cyan")
        dependents_table.add_column("Required By", style="green")

        for tool in sorted(tool_registry._tools.keys()):
            dependents = graph.get_dependents(tool)
            if dependents:
                dependents_table.add_row(tool, ", ".join(dependents))

        if dependents_table.rows:
            display.console.print(dependents_table)
        else:
            display.console.print("[dim]No dependents[/]")


@main.command()
@click.option("--limit", "-n", default=10, help="Number of traces to show")
@click.option("--trace-id", "-t", default=None, help="Filter by trace ID")
@click.option("--tree", "show_tree", is_flag=True, help="Show as tree structure")
@click.option("--json", "output_json", is_flag=True, help="Output as JSON")
@click.option("--enable", is_flag=True, help="Enable tracing for current session")
@click.pass_context
def trace(
    ctx, limit: int, trace_id: Optional[str], show_tree: bool, output_json: bool, enable: bool
):
    """Show recent OpenTelemetry traces.

    Displays trace spans from recent agent executions including:
    - Agent node execution (think, plan, act, observe, reflect)
    - Tool calls with parameters and duration
    - LLM calls with model and token usage

    Examples:
        mini-claude trace                    # Show last 10 traces
        mini-claude trace -n 20              # Show last 20 traces
        mini-claude trace -t <trace_id>      # Show specific trace
        mini-claude trace --tree             # Show as tree
        mini-claude trace --enable           # Enable tracing
        mini-claude trace --json             # JSON output
    """
    from mini_claude.monitoring.tracing import (
        get_tracing_manager,
        get_recent_traces,
        get_trace_tree,
    )
    from mini_claude.config.settings import settings
    from rich.table import Table
    from rich.tree import Tree as RichTree

    # Handle enable flag
    if enable:
        manager = get_tracing_manager()
        if not manager.enabled:
            success = manager.setup(
                service_name=settings.tracing_service_name,
                exporter_type=settings.tracing_exporter,
            )
            if success:
                display.console.print("[green]Tracing enabled[/]")
            else:
                display.console.print(
                    "[red]Failed to enable tracing. Check OpenTelemetry installation.[/]"
                )
        else:
            display.console.print("[dim]Tracing already enabled[/]")
        return

    # Handle tree view
    if show_tree:
        tree_data = get_trace_tree(trace_id)

        if "error" in tree_data:
            display.console.print(f"[yellow]{tree_data['error']}[/]")
            return

        if output_json:
            import json

            print(json.dumps(tree_data, indent=2))
            return

        def build_tree(data: dict, parent: RichTree) -> None:
            for span in data.get("spans", []):
                status_color = (
                    "green"
                    if span["status"] == "OK"
                    else "red"
                    if span["status"] == "ERROR"
                    else "dim"
                )
                node = parent.add(
                    f"[cyan]{span['name']}[/] [{status_color}]{span['status']}[/{status_color}] ({span['duration_ms']:.1f}ms)"
                )
                for child in span.get("children", []):
                    build_tree({"spans": [child]}, node)

        root = RichTree(f"[bold]Trace: {tree_data['trace_id']}[/]")
        build_tree(tree_data, root)
        display.console.print(root)
        return

    # Get traces
    traces = get_recent_traces(limit)

    if trace_id:
        traces = [t for t in traces if t["trace_id"] == trace_id]

    if not traces:
        display.console.print("[dim]No traces available. Run some commands first.[/]")
        display.console.print(
            "[dim]Tip: Enable tracing with 'mini-claude trace --enable' or set TRACING_ENABLED=true[/]"
        )
        return

    if output_json:
        import json

        print(json.dumps(traces, indent=2))
        return

    # Display as table
    table = Table(title="Recent Traces")
    table.add_column("Trace ID", style="dim", max_width=16)
    table.add_column("Span", style="cyan")
    table.add_column("Duration", style="green")
    table.add_column("Status", style="bold")
    table.add_column("Attributes", style="dim", max_width=30)

    for t in traces:
        trace_id_short = t["trace_id"][:16] if t["trace_id"] else "N/A"
        status = t["status"]
        status_color = "green" if status == "OK" else "red" if status == "ERROR" else "yellow"

        # Format attributes
        attrs = t.get("attributes", {})
        attrs_str = ", ".join(f"{k}={v}" for k, v in list(attrs.items())[:3])
        if len(attrs) > 3:
            attrs_str += "..."

        table.add_row(
            trace_id_short,
            t["name"],
            f"{t['duration_ms']:.1f}ms",
            f"[{status_color}]{status}[/{status_color}]",
            attrs_str[:30] if attrs_str else "-",
        )

    display.console.print(table)

    # Show tracing status
    manager = get_tracing_manager()
    status = "enabled" if manager.enabled else "disabled"
    status_color = "green" if manager.enabled else "yellow"
    display.console.print(
        f"\n[dim]Tracing: [{status_color}]{status}[/{status_color}] | Exporter: {settings.tracing_exporter}[/]"
    )


if __name__ == "__main__":
    main()
