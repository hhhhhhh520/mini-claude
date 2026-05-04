"""Alert command handler for alert management.

Commands:
    /alerts - Show alert status
    /alerts ack <id> - Acknowledge an alert
    /alerts clear - Clear all alerts
    /alerts check - Trigger manual alert check
"""

from rich.table import Table

from .base import CommandHandler, CommandContext, CommandResult
from ...monitoring.alerts import get_alert_manager, acknowledge_alert


class AlertCommandHandler(CommandHandler):
    """Handle alert management commands."""

    commands = ["/alerts"]

    async def handle(self, ctx: CommandContext) -> CommandResult:
        """Handle /alerts command."""
        args = ctx.args.strip()

        if args.startswith("ack "):
            return self._acknowledge_alert(ctx, args[4:].strip())

        if args == "clear":
            return self._clear_alerts(ctx)

        if args == "check":
            return self._check_alerts(ctx)

        # Default: show alert status
        return self._show_status(ctx)

    def _acknowledge_alert(self, ctx: CommandContext, alert_id: str) -> CommandResult:
        """Acknowledge an alert."""
        if acknowledge_alert(alert_id):
            return CommandResult(
                handled=True,
                message=f"[green]Alert {alert_id} acknowledged[/]",
            )
        return CommandResult(
            handled=True,
            message=f"[yellow]Alert {alert_id} not found[/]",
        )

    def _clear_alerts(self, ctx: CommandContext) -> CommandResult:
        """Clear all alerts."""
        manager = get_alert_manager()
        count = manager.clear_all_alerts()
        return CommandResult(
            handled=True,
            message=f"[green]Cleared {count} alerts[/]",
        )

    def _check_alerts(self, ctx: CommandContext) -> CommandResult:
        """Trigger manual alert check."""
        from ...monitoring.metrics import get_metrics_collector
        collector = get_metrics_collector()
        alerts = collector.check_alerts()

        if alerts:
            ctx.display.console.print(f"[yellow]Triggered {len(alerts)} alerts[/]")
            for alert in alerts:
                ctx.display.console.print(f"  [{alert.level.value}] {alert.message}")
            return CommandResult(handled=True)

        return CommandResult(
            handled=True,
            message="[green]No alerts triggered[/]",
        )

    def _show_status(self, ctx: CommandContext) -> CommandResult:
        """Show alert status."""
        manager = get_alert_manager()
        status = manager.get_status()
        active_alerts = manager.get_active_alerts()

        # Status table
        status_table = Table(title="Alert System Status")
        status_table.add_column("Metric", style="cyan")
        status_table.add_column("Value", style="white")

        status_table.add_row("Enabled", str(status["enabled"]))
        status_table.add_row("Rules", str(status["rules_count"]))
        status_table.add_row("Handlers", str(status["handlers_count"]))
        status_table.add_row("Active Alerts", str(status["active_alerts"]))
        status_table.add_row("Acknowledged", str(status["acknowledged_alerts"]))

        if status["silenced_rules"]:
            status_table.add_row("Silenced Rules", ", ".join(status["silenced_rules"]))

        ctx.display.console.print(status_table)

        # Active alerts table
        if active_alerts:
            alerts_table = Table(title="Active Alerts")
            alerts_table.add_column("ID", style="dim")
            alerts_table.add_column("Level", style="yellow")
            alerts_table.add_column("Rule", style="cyan")
            alerts_table.add_column("Message", style="white")
            alerts_table.add_column("Time", style="dim")

            for alert in active_alerts[:10]:  # Show max 10
                level_style = {
                    "info": "blue",
                    "warning": "yellow",
                    "error": "red",
                    "critical": "red bold",
                }.get(alert.level.value, "white")

                alerts_table.add_row(
                    alert.alert_id,
                    f"[{level_style}]{alert.level.value}[/{level_style}]",
                    alert.rule_name,
                    alert.message[:50] + ("..." if len(alert.message) > 50 else ""),
                    alert.timestamp.strftime("%H:%M:%S"),
                )

            ctx.display.console.print(alerts_table)
            ctx.display.console.print("\n[dim]Use /alerts ack <id> to acknowledge[/]")
        else:
            ctx.display.console.print("\n[green]No active alerts[/]")

        return CommandResult(handled=True)

    def get_help_text(self) -> str:
        """Get help text for alert commands."""
        return (
            "/alerts - Show active alerts and alert status\n"
            "  /alerts ack <id> - Acknowledge an alert\n"
            "  /alerts clear - Clear all alerts\n"
            "  /alerts check - Trigger manual alert check"
        )