"""Help command handler for displaying help information.

Commands:
    /help - Show help
    /? - Show help
    /exit, /quit, /q - Exit REPL
    /clear - Clear screen
    /model <name> - Switch model
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
            model = ctx.args.strip()
            if model:
                return CommandResult(
                    handled=True,
                    message=f"[dim]Model switched to: {model}[/]",
                )
            return CommandResult(
                handled=True,
                message="[dim]Usage: /model <name>[/]",
            )

        return CommandResult(handled=False)

    def _show_help(self, ctx: CommandContext) -> CommandResult:
        """Display help information."""
        help_text = """[bold]Commands:[/]
/help - Show this help
/exit, /quit, /q - Exit REPL
/clear - Clear screen
/model <name> - Switch model
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
/config-watch [start|stop|status] - Manage config file watching"""

        ctx.display.console.print(Panel.fit(help_text, title="Help"))
        return CommandResult(handled=True)

    def get_help_text(self) -> str:
        """Get help text for basic commands."""
        return (
            "/help, /? - Show this help\n"
            "/exit, /quit, /q - Exit REPL\n"
            "/clear - Clear screen\n"
            "/model <name> - Switch model"
        )
