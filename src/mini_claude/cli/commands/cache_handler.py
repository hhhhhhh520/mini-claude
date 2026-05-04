"""Cache command handler for tool cache management.

Commands:
    /cache - Show cache status
    /cache status - Show cache status
    /cache clear - Clear cache
    /cache invalidate <tool> - Invalidate tool cache
    /cache cleanup - Cleanup expired entries
"""

from rich.table import Table

from .base import CommandHandler, CommandContext, CommandResult
from ...config.settings import settings


class CacheCommandHandler(CommandHandler):
    """Handle cache management commands."""

    commands = ["/cache"]

    async def handle(self, ctx: CommandContext) -> CommandResult:
        """Handle /cache command."""
        args = ctx.args.strip()

        if not settings.tool_cache_enabled:
            return CommandResult(
                handled=True,
                message="[yellow]Tool cache is disabled in settings[/]",
            )

        from ...tools.cache import get_tool_cache
        cache = get_tool_cache()

        if not args or args == "status":
            return self._show_status(ctx, cache)

        if args == "clear":
            return self._clear_cache(ctx, cache)

        if args.startswith("invalidate "):
            return self._invalidate_tool(ctx, cache, args[11:].strip())

        if args == "cleanup":
            return self._cleanup_expired(ctx, cache)

        return CommandResult(
            handled=True,
            message="[dim]Usage: /cache [status|clear|invalidate <tool>|cleanup][/]",
        )

    def _show_status(self, ctx: CommandContext, cache) -> CommandResult:
        """Show cache status."""
        stats = cache.get_stats()
        table = Table(title="Tool Cache Status")
        table.add_column("Metric", style="cyan")
        table.add_column("Value", style="white")

        table.add_row("Cache Size", f"{stats['size']} / {stats['max_size']}")
        table.add_row("Hit Rate", f"{stats['hit_rate']}%")
        table.add_row("Total Hits", str(stats["hits"]))
        table.add_row("Total Misses", str(stats["misses"]))
        table.add_row("TTL (seconds)", str(stats["ttl_seconds"]))
        table.add_row("Cacheable Tools", ", ".join(stats["cacheable_tools"]))

        ctx.display.console.print(table)

        # Show entries if any
        if stats["size"] > 0:
            entries = cache.get_entries()
            if entries:
                ctx.display.console.print("\n[bold]Cached Entries:[/]")
                entry_table = Table()
                entry_table.add_column("Tool", style="cyan")
                entry_table.add_column("TTL Remaining", style="green")
                entry_table.add_column("Hits", style="yellow")

                for entry in entries[:10]:  # Show top 10
                    entry_table.add_row(
                        entry["tool_name"],
                        f"{entry['ttl_remaining']}s",
                        str(entry["hit_count"]),
                    )
                ctx.display.console.print(entry_table)

        return CommandResult(handled=True)

    def _clear_cache(self, ctx: CommandContext, cache) -> CommandResult:
        """Clear all cache entries."""
        count = cache.clear()
        return CommandResult(
            handled=True,
            message=f"[green]Cleared {count} cache entries[/]",
        )

    def _invalidate_tool(self, ctx: CommandContext, cache, tool_name: str) -> CommandResult:
        """Invalidate cache for a specific tool."""
        count = cache.invalidate(tool_name)
        return CommandResult(
            handled=True,
            message=f"[green]Invalidated {count} entries for tool: {tool_name}[/]",
        )

    def _cleanup_expired(self, ctx: CommandContext, cache) -> CommandResult:
        """Cleanup expired entries."""
        count = cache.cleanup_expired()
        return CommandResult(
            handled=True,
            message=f"[green]Removed {count} expired entries[/]",
        )

    def get_help_text(self) -> str:
        """Get help text for cache commands."""
        return (
            "/cache - View or manage tool cache\n"
            "  /cache status - Show cache status\n"
            "  /cache clear - Clear cache\n"
            "  /cache invalidate <tool> - Invalidate tool cache\n"
            "  /cache cleanup - Cleanup expired entries"
        )
