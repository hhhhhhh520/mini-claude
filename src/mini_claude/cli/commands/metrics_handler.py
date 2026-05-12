"""Metrics command handler for monitoring and token tracking.

Commands:
    /status - Show session status (including token usage)
    /tokens - Show detailed token usage
    /metrics - Show Prometheus metrics
"""

from rich.table import Table
from langchain_core.messages import AIMessage

from .base import CommandHandler, CommandContext, CommandResult
from ...utils.token_manager import get_token_counter
from ...config.settings import settings


class MetricsCommandHandler(CommandHandler):
    """Handle metrics and status commands."""

    commands = ["/status", "/tokens", "/metrics"]

    async def handle(self, ctx: CommandContext) -> CommandResult:
        """Handle metrics commands."""
        cmd = ctx.command

        if cmd == "/status":
            return self._show_status(ctx)

        if cmd == "/tokens":
            return self._show_tokens(ctx)

        if cmd == "/metrics":
            return self._show_metrics(ctx)

        return CommandResult(handled=False)

    def _get_messages_for_counting(self, ctx: CommandContext) -> list:
        """Convert messages to dict format for token counting."""
        messages_for_count = []
        for msg in ctx.messages:
            if isinstance(msg, dict):
                messages_for_count.append(msg)
            else:
                # LangChain message
                role = (
                    "user"
                    if hasattr(msg, "content") and not isinstance(msg, AIMessage)
                    else "assistant"
                )
                if hasattr(msg, "content"):
                    messages_for_count.append({"role": role, "content": msg.content})
        return messages_for_count

    def _show_status(self, ctx: CommandContext) -> CommandResult:
        """Show session status with token usage."""
        model = settings.default_model
        token_counter = get_token_counter(model)

        messages_for_count = self._get_messages_for_counting(ctx)
        stats = token_counter.get_usage_stats(messages_for_count)

        ctx.display.console.print(f"[dim]Messages in history: {len(ctx.messages)}[/]")
        ctx.display.console.print(f"[dim]Thread ID: {ctx.thread_id}[/]")
        ctx.display.console.print(f"[dim]Model: {model}[/]")
        ctx.display.console.print(
            f"[dim]Tokens: {stats['current_tokens']} / {stats['token_budget']} "
            f"({stats['usage_percent']}%)[/]"
        )

        if stats["is_near_limit"]:
            ctx.display.console.print("[yellow]Warning Approaching token limit[/]")

        return CommandResult(handled=True)

    def _show_tokens(self, ctx: CommandContext) -> CommandResult:
        """Show detailed token usage."""
        model = settings.default_model
        token_counter = get_token_counter(model)

        messages_for_count = self._get_messages_for_counting(ctx)
        stats = token_counter.get_usage_stats(messages_for_count)

        # Create table
        table = Table(title="Token Usage Statistics")
        table.add_column("Metric", style="cyan")
        table.add_column("Value", style="green")

        table.add_row("Model", stats["model"])
        table.add_row("Context Window", str(stats["context_window"]))
        table.add_row("Token Budget", str(stats["token_budget"]))
        table.add_row("Current Tokens", str(stats["current_tokens"]))
        table.add_row("Usage", f"{stats['usage_percent']}%")
        table.add_row("Available", str(stats["available_for_input"]))
        table.add_row("Reserved Output", str(stats["reserved_output"]))

        ctx.display.console.print(table)

        # Status indicator
        if stats["is_over_budget"]:
            ctx.display.console.print("[red]X Token budget exceeded![/]")
        elif stats["is_near_limit"]:
            ctx.display.console.print("[yellow]Warning Approaching token limit[/]")
        else:
            ctx.display.console.print("[green]OK Within budget[/]")

        return CommandResult(handled=True)

    def _show_metrics(self, ctx: CommandContext) -> CommandResult:
        """Show Prometheus metrics summary."""
        from ...monitoring.metrics import get_metrics_summary

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

        ctx.display.console.print(requests_table)

        # Tokens table
        tokens_table = Table(title="Token Usage")
        tokens_table.add_column("Type", style="cyan")
        tokens_table.add_column("Count", style="green")

        tokens = summary["tokens"]
        tokens_table.add_row("Input", str(tokens["input"]))
        tokens_table.add_row("Output", str(tokens["output"]))
        tokens_table.add_row("Total", str(tokens["total"]))

        ctx.display.console.print(tokens_table)

        # Tools table
        tools = summary["tools"]
        all_tools = set(tools["success"].keys()) | set(tools["failure"].keys())
        if all_tools:
            tools_table = Table(title="Tool Calls")
            tools_table.add_column("Tool", style="cyan")
            tools_table.add_column("Success", style="green")
            tools_table.add_column("Failure", style="red")

            for tool_name in sorted(all_tools):
                success_count = tools["success"].get(tool_name, 0)
                failure_count = tools["failure"].get(tool_name, 0)
                tools_table.add_row(tool_name, str(success_count), str(failure_count))

            ctx.display.console.print(tools_table)

        # Performance
        perf = summary["performance"]
        ctx.display.console.print(
            f"\n[dim]Avg Duration: {perf['avg_duration_seconds']}s | "
            f"Total: {perf['total_duration_seconds']}s | "
            f"Uptime: {summary['uptime_seconds']:.1f}s[/]"
        )

        return CommandResult(handled=True)

    def get_help_text(self) -> str:
        """Get help text for metrics commands."""
        return (
            "/status - Show session status (including token usage)\n"
            "/tokens - Show detailed token usage\n"
            "/metrics - Show Prometheus metrics"
        )
