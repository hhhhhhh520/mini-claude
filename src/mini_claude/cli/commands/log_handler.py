"""Log command handler for execution log export.

Commands:
    /export-log [format] [path] - Export execution log
        format: json, markdown, html (default: json)
        path: optional file path
"""

from .base import CommandHandler, CommandContext, CommandResult


class LogCommandHandler(CommandHandler):
    """Handle log export commands."""

    commands = ["/export-log"]

    async def handle(self, ctx: CommandContext) -> CommandResult:
        """Handle /export-log command."""
        args = ctx.args.strip()

        from ...utils.logger import get_execution_log_exporter
        exporter = get_execution_log_exporter()

        # Parse arguments
        parts = args.split() if args else []

        # Determine format
        export_format = "json"
        if parts and parts[0].lower() in ("json", "markdown", "md", "html"):
            export_format = parts[0].lower()
            if export_format == "md":
                export_format = "markdown"
            parts = parts[1:]

        # Determine path
        export_path = parts[0] if parts else None

        try:
            if export_path:
                # Export to file
                exporter.export_to_file(
                    session_id=ctx.thread_id,
                    format=export_format,
                    path=export_path,
                    include_metrics=True,
                    include_audit=True,
                )
                return CommandResult(
                    handled=True,
                    message=f"[green]Exported log to: {export_path}[/]",
                )

            # Export to console
            if export_format == "json":
                output = exporter.export_json(
                    session_id=ctx.thread_id,
                    include_metrics=True,
                    include_audit=True,
                )
            elif export_format == "markdown":
                output = exporter.export_markdown(
                    session_id=ctx.thread_id,
                    include_metrics=True,
                    include_audit=True,
                )
            else:  # html
                output = exporter.export_html(
                    session_id=ctx.thread_id,
                    include_metrics=True,
                    include_audit=True,
                )

            # Print output (truncate if too long)
            if len(output) > 5000:
                ctx.display.console.print(output[:5000])
                ctx.display.console.print(
                    f"\n[dim]... output truncated ({len(output)} total characters)[/]"
                )
            else:
                ctx.display.console.print(output)

            return CommandResult(handled=True)

        except Exception as e:
            return CommandResult(
                handled=True,
                error=f"Export failed: {e}",
            )

    def get_help_text(self) -> str:
        """Get help text for log commands."""
        return (
            "/export-log [format] [path] - Export execution log\n"
            "  format: json, markdown, html (default: json)\n"
            "  path: optional file path"
        )
