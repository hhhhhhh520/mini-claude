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
@click.pass_context
def ask(ctx, prompt: str, model: Optional[str], output_json: bool):
    """Execute a single prompt and exit."""
    import json
    from ..llm.provider import LLMProvider, convert_tools_to_litellm
    from ..tools import get_all_tools, execute_tool

    load_environment()

    async def run_single():
        llm = LLMProvider(model)
        display.user_message(prompt)
        display.show_thinking()

        # Get tools
        tools = get_all_tools()
        litellm_tools = convert_tools_to_litellm(tools)

        messages = [{"role": "user", "content": prompt}]

        try:
            # First call with tools
            response = await llm.chat(
                messages=messages,
                tools=litellm_tools,
                tool_choice="auto",
            )

            message = response.choices[0].message

            # Check for tool calls
            if hasattr(message, "tool_calls") and message.tool_calls:
                # Execute tools
                for tc in message.tool_calls:
                    tool_name = tc.function.name
                    tool_args = tc.function.arguments

                    if isinstance(tool_args, str):
                        tool_args = json.loads(tool_args)

                    print(f"[Tool] {tool_name}({tool_args})")
                    result = await execute_tool(tool_name, tool_args)

                    # Add assistant message and tool result
                    messages.append({"role": "assistant", "content": message.content or ""})
                    messages.append({"role": "user", "content": f"Tool {tool_name} result: {result}"})

                # Second call to process tool results
                response = await llm.chat(messages=messages)
                result_text = response.choices[0].message.content
            else:
                result_text = message.content or ""

            display.agent_message(result_text)
            return result_text
        except Exception as e:
            display.show_error(str(e))
            return None

    asyncio.run(run_single())


@main.command()
@click.pass_context
def status(ctx):
    """Show current status."""
    from mini_claude.config.settings import settings

    display.console.print(Panel.fit(
        f"[bold]Model:[/] {settings.default_model}\n"
        f"[bold]Workspace:[/] {settings.workspace_root}\n"
        f"[bold]Max Sub-Agents:[/] {settings.max_sub_agents}\n"
        f"[bold]Max Iterations:[/] {settings.max_iterations}",
        title="Status",
    ))


@main.command()
@click.argument("model")
@click.pass_context
def model(ctx, model: str):
    """Switch default model."""
    # This would need to update settings
    display.console.print(f"[dim]Model set to: {model}[/]")


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
            display.console.print(Panel.fit(
                f"[bold]Status:[/] {report.service.status.value}\n"
                f"[bold]Uptime:[/] {report.service.to_dict()['uptime_human']}\n"
                f"[bold]Memory:[/] {report.service.memory_usage_mb:.1f} MB\n"
                f"[bold]CPU:[/] {report.service.cpu_percent:.1f}%",
                title="Service",
            ))

            # Model status
            model_status_color = "green" if report.model.status == HealthStatus.HEALTHY else "red"
            display.console.print(Panel.fit(
                f"[bold]Status:[/] [{model_status_color}]{report.model.status.value}[/{model_status_color}]\n"
                f"[bold]Model:[/] {report.model.model_name}\n"
                f"[bold]Provider:[/] {report.model.provider}" +
                (f"\n[bold]Response Time:[/] {report.model.response_time_ms:.0f}ms" if report.model.response_time_ms else "") +
                (f"\n[bold]Error:[/] {report.model.error_message}" if report.model.error_message else ""),
                title="Model",
            ))

            # Tools status
            display.console.print(Panel.fit(
                f"[bold]Status:[/] {report.tools.status.value}\n"
                f"[bold]Available:[/] {report.tools.available_tools}/{report.tools.total_tools}\n"
                f"[bold]Tools:[/] {', '.join(report.tools.tool_names[:5])}" +
                (f" (+{len(report.tools.tool_names) - 5} more)" if len(report.tools.tool_names) > 5 else ""),
                title="Tools",
            ))

            # Overall status
            overall_color = "green" if report.overall_status() == HealthStatus.HEALTHY else "yellow" if report.overall_status() == HealthStatus.DEGRADED else "red"
            display.console.print(f"\n[bold]Overall Status:[/] [{overall_color}]{report.overall_status().value}[/{overall_color}]")

        return report

    # Import HealthStatus for display
    from mini_claude.monitoring.health import HealthStatus

    asyncio.run(run_check())


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
    asyncio.run(run_health_server(port=port, run=True))


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
        display.console.print(Panel.fit(
            f"[bold]Avg Duration:[/] {perf['avg_duration_seconds']}s\n"
            f"[bold]Total Duration:[/] {perf['total_duration_seconds']}s\n"
            f"[bold]Uptime:[/] {summary['uptime_seconds']:.1f}s",
            title="Performance",
        ))


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

    graph = get_dependency_graph()

    if output_json:
        import json
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
            return

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

        display.console.print(Panel.fit(
            f"[bold]Direct Dependencies:[/]\n{deps_text}\n\n"
            f"[bold]All Dependencies (transitive):[/]\n{all_deps_text}\n\n"
            f"[bold]Dependents:[/]\n{dependents_text}",
            title=f"Tool: {tool_name}",
        ))

        # Availability status
        if available:
            display.console.print("[green]All required dependencies available[/]")
        else:
            display.console.print(
                f"[red]Missing required: {missing_required}[/]"
            )

        if missing_optional:
            display.console.print(
                f"[yellow]Missing optional: {missing_optional}[/]"
            )

    else:
        # Show entire dependency graph
        display.console.print(Panel.fit(
            f"[bold]Total Tools with Dependencies:[/] {len(graph._dependencies)}\n"
            f"[bold]Registered Tools:[/] {len(tool_registry._tools)}",
            title="Tool Dependency Graph",
        ))

        # Build tree visualization
        tree = Tree("[bold]Dependencies[/]")

        for tool, deps in sorted(graph._dependencies.items()):
            tool_node = tree.add(f"[cyan]{tool}[/]")
            for dep in deps:
                for d in dep.depends_on:
                    status = "[green]available[/]" if d in tool_registry._tools else "[red]missing[/]"
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
def trace(ctx, limit: int, trace_id: Optional[str], show_tree: bool, output_json: bool, enable: bool):
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
                display.console.print("[red]Failed to enable tracing. Check OpenTelemetry installation.[/]")
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
                status_color = "green" if span["status"] == "OK" else "red" if span["status"] == "ERROR" else "dim"
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
        display.console.print("[dim]Tip: Enable tracing with 'mini-claude trace --enable' or set TRACING_ENABLED=true[/]")
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
    display.console.print(f"\n[dim]Tracing: [{status_color}]{status}[/{status_color}] | Exporter: {settings.tracing_exporter}[/]")


if __name__ == "__main__":
    main()
