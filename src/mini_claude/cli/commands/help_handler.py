"""Help command handler for displaying help information.

Commands:
    /help - Show help
    /? - Show help
    /exit, /quit, /q - Exit REPL
    /clear - Clear screen
    /model [name] - Show current model or hot-switch to <name>
"""

from rich.panel import Panel

from .base import CommandHandler, CommandContext, CommandResult


class HelpCommandHandler(CommandHandler):
    """Handle help and basic commands."""

    commands = [
        "/help",
        "/?",
        "/exit",
        "/quit",
        "/q",
        "/clear",
        "/model",
    ]

    async def handle(self, ctx: CommandContext) -> CommandResult:
        """Handle help and basic commands."""
        cmd = ctx.command

        if cmd in ("/exit", "/quit", "/q"):
            return CommandResult(
                handled=True,
                message="[dim]Goodbye![/]",
                exit_repl=True,
            )

        if cmd in ("/help", "/?"):
            return self._show_help(ctx)

        if cmd == "/clear":
            ctx.display.console.clear()
            return CommandResult(handled=True)

        if cmd == "/model":
            # P4-4：热切换——改 settings.default_model 并重建 provider 单例
            from ...agent.nodes import _shared
            from ...config.settings import settings as app_settings

            args = (ctx.args or "").strip()
            if not args:
                return CommandResult(
                    handled=True,
                    message=f"当前模型: {app_settings.default_model}\n"
                    "切换: /model <model-name>（.env 的 DEFAULT_MODEL 仍是下次启动默认）",
                )
            old = app_settings.default_model
            app_settings.default_model = args
            _shared.rebuild_llm_provider(args)
            return CommandResult(
                handled=True,
                message=f"模型已切换: {old} → {args}\n"
                "（本会话即时生效，含子代理；.env 默认值未改动）",
            )

        return CommandResult(handled=False)

    def _show_help(self, ctx: CommandContext) -> CommandResult:
        """Display help information."""
        help_text = """[bold]Commands:[/]
/help - Show this help
/exit, /quit, /q - Exit REPL
/clear - Clear screen
/model [name] - Show current model or hot-switch to <name>
/status - Show session status (including token usage)
/tokens - Show detailed token usage
/metrics - Show Prometheus metrics
/alerts - Show active alerts and alert status
/reset - Clear conversation history
/thread <id> - Switch to a new thread
/resume <id> - Resume a saved thread (with checkpoint recovery)
/interrupted - List interrupted sessions available for recovery
/save [id] - Save current session
/load <id> - Load a saved session
/sessions - List saved sessions
/profile - View or edit user profile
/cache - View or manage tool cache
/export-log [format] [path] - Export execution log (json/markdown/html)
/reload-config - Reload configuration from .env file
/config-watch [start|stop|status] - Manage config file watching
/skills - List all available skills
/skill <name> [args] - Invoke a skill
/mcp [connect|disconnect|reload] - Manage MCP servers and tools
/rewind [n] - List turn checkpoints or rewind to #n (fork re-run)
/permissions [mode] - View or switch permission mode (shift+tab cycles)
/hooks - View configured hooks (PreToolUse/PostToolUse/Stop)"""

        ctx.display.console.print(Panel.fit(help_text, title="Help"))
        return CommandResult(handled=True)

    def get_help_text(self) -> str:
        """Get help text for basic commands."""
        return (
            "/help, /? - Show this help\n"
            "/exit, /quit, /q - Exit REPL\n"
            "/clear - Clear screen\n"
            "/model [name] - Show current model or hot-switch to <name>"
        )
