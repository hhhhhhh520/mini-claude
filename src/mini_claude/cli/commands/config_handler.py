"""Config command handler for configuration management.

Commands:
    /reload-config - Reload configuration from .env file
    /config-watch [start|stop|status] - Manage config file watching
"""

from rich.table import Table

from .base import CommandHandler, CommandContext, CommandResult
from ...config.settings import settings


class ConfigCommandHandler(CommandHandler):
    """Handle configuration management commands."""

    commands = ["/reload-config", "/config-watch"]

    async def handle(self, ctx: CommandContext) -> CommandResult:
        """Handle config commands."""
        cmd = ctx.command

        if cmd == "/reload-config":
            return self._reload_config(ctx)

        if cmd == "/config-watch":
            return self._config_watch(ctx, ctx.args.strip())

        return CommandResult(handled=False)

    def _reload_config(self, ctx: CommandContext) -> CommandResult:
        """Reload configuration from .env file."""
        result = settings.reload()

        if result.success:
            if result.has_changes():
                # Show changes
                table = Table(title="Configuration Reloaded")
                table.add_column("Setting", style="cyan")
                table.add_column("Old Value", style="red")
                table.add_column("New Value", style="green")

                for change in result.changes[:20]:  # Show max 20 changes
                    old_str = str(change.old_value)[:30]
                    new_str = str(change.new_value)[:30]
                    table.add_row(change.key, old_str, new_str)

                ctx.display.console.print(table)

                if len(result.changes) > 20:
                    ctx.display.console.print(
                        f"[dim]... and {len(result.changes) - 20} more changes[/]"
                    )

                return CommandResult(
                    handled=True,
                    message=f"[green]Successfully reloaded {len(result.changes)} configuration changes[/]",
                )

            return CommandResult(
                handled=True,
                message="[dim]No configuration changes detected[/]",
            )

        return CommandResult(
            handled=True,
            error=f"Failed to reload configuration: {result.error}",
        )

    def _config_watch(self, ctx: CommandContext, args: str) -> CommandResult:
        """Manage config file watching."""
        from ...config.watcher import stop_config_watcher

        if args == "start":
            return self._start_watcher(ctx)

        if args == "stop":
            stop_config_watcher()
            return CommandResult(
                handled=True,
                message="[dim]Config file watching stopped[/]",
            )

        # Default: show status
        return self._show_watcher_status(ctx)

    def _start_watcher(self, ctx: CommandContext) -> CommandResult:
        """Start config watcher."""
        if not settings.config_watch_enabled:
            return CommandResult(
                handled=True,
                message="[yellow]Config watching is disabled. Set config_watch_enabled=true in .env[/]",
            )

        from ...config.watcher import get_config_watcher
        watcher = get_config_watcher(settings)

        if watcher.start():
            return CommandResult(
                handled=True,
                message="[green]Config file watching started[/]",
            )

        return CommandResult(
            handled=True,
            message="[yellow]Failed to start config watcher (file may not exist)[/]",
        )

    def _show_watcher_status(self, ctx: CommandContext) -> CommandResult:
        """Show config watcher status."""
        from ...config.watcher import get_config_watcher
        from datetime import datetime

        watcher = get_config_watcher(settings)
        state = watcher.get_state()

        table = Table(title="Config Watcher Status")
        table.add_column("Property", style="cyan")
        table.add_column("Value", style="white")

        table.add_row("Enabled in Settings", str(settings.config_watch_enabled))
        table.add_row("Currently Watching", str(state.watching))
        table.add_row("Config Path", str(watcher.config_path))
        table.add_row("Debounce (seconds)", str(settings.config_watch_debounce_seconds))

        if state.last_mtime > 0:
            last_mod = datetime.fromtimestamp(state.last_mtime)
            table.add_row("Last Modification", last_mod.strftime("%Y-%m-%d %H:%M:%S"))

        ctx.display.console.print(table)

        if not settings.config_watch_enabled:
            ctx.display.console.print(
                "\n[dim]Tip: Add config_watch_enabled=true to .env to enable auto-reload[/]"
            )

        return CommandResult(handled=True)

    def get_help_text(self) -> str:
        """Get help text for config commands."""
        return (
            "/reload-config - Reload configuration from .env file\n"
            "/config-watch [start|stop|status] - Manage config file watching"
        )
