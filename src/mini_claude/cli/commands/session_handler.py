"""Session command handler for session management.

Commands:
    /save [id] - Save current session
    /load <id> - Load a saved session
    /resume <id> - Resume a saved thread (with checkpoint recovery)
    /sessions - List saved sessions
    /interrupted - List interrupted sessions available for recovery
"""

from rich.table import Table

from .base import CommandHandler, CommandContext, CommandResult
from ...utils.session import get_session_manager
from ...utils.token_manager import count_messages_tokens


class SessionCommandHandler(CommandHandler):
    """Handle session management commands."""

    commands = [
        "/save",
        "/load",
        "/resume",
        "/sessions",
        "/interrupted",
        "/reset",
        "/thread",
    ]

    async def handle(self, ctx: CommandContext) -> CommandResult:
        """Handle session commands."""
        cmd = ctx.command
        args = ctx.args.strip()

        if cmd == "/save":
            return self._save_session(ctx, args or "default")

        if cmd == "/load":
            if not args:
                return CommandResult(
                    handled=True,
                    message="[red]Usage: /load <session_id>[/]",
                )
            return self._load_session(ctx, args)

        if cmd == "/resume":
            if not args:
                return CommandResult(
                    handled=True,
                    message="[red]Usage: /resume <thread_id>[/]",
                )
            return self._resume_session(ctx, args)

        if cmd == "/sessions":
            return self._list_sessions(ctx)

        if cmd == "/interrupted":
            return self._list_interrupted(ctx)

        if cmd == "/reset":
            return self._reset_session(ctx)

        if cmd == "/thread":
            if not args:
                return CommandResult(
                    handled=True,
                    message="[red]Usage: /thread <id>[/]",
                )
            return self._switch_thread(ctx, args)

        return CommandResult(handled=False)

    def _save_session(self, ctx: CommandContext, session_id: str) -> CommandResult:
        """Save current session."""
        manager = get_session_manager()
        token_count = count_messages_tokens(ctx.messages)
        manager.save_session(
            session_id,
            ctx.messages,
            summary=ctx.session.summary,
            token_count=token_count,
        )
        return CommandResult(
            handled=True,
            message=f"[dim]Session saved as: {session_id}[/]",
        )

    def _load_session(self, ctx: CommandContext, session_id: str) -> CommandResult:
        """Load a saved session."""
        manager = get_session_manager()
        loaded, summary = manager.load_session(session_id)

        if loaded:
            ctx.messages = loaded
            ctx.session.summary = summary
            return CommandResult(
                handled=True,
                message=f"[dim]Session loaded: {session_id} ({len(loaded)} messages)[/]",
            )

        return CommandResult(
            handled=True,
            message=f"[dim]Session not found: {session_id}[/]",
        )

    def _resume_session(self, ctx: CommandContext, thread_id: str) -> CommandResult:
        """Resume session with checkpoint recovery."""
        manager = get_session_manager()

        # Check for execution state (checkpoint recovery)
        exec_state = manager.load_execution_state(thread_id)
        if exec_state:
            ctx.display.console.print(f"[yellow]Found interrupted session: {thread_id}[/]")
            ctx.display.console.print(f"[dim]  Current node: {exec_state.current_node}[/]")
            ctx.display.console.print(f"[dim]  Iterations: {exec_state.iteration_count}[/]")
            if exec_state.last_error:
                ctx.display.console.print(f"[dim]  Last error: {exec_state.last_error[:50]}...[/]")
            ctx.display.console.print("[dim]Resuming from checkpoint...[/]")

            # Load messages as well
            loaded, summary = manager.load_session(thread_id)
            if loaded:
                ctx.messages = loaded
                ctx.session.summary = summary

            ctx.thread_id = thread_id
            ctx.session._execution_state = exec_state

            return CommandResult(
                handled=True,
                message=f"[green]Session resumed from checkpoint: {thread_id}[/]",
            )

        # Fallback: regular message resume
        loaded, summary = manager.load_session(thread_id)
        if loaded:
            ctx.messages = loaded
            ctx.thread_id = thread_id
            ctx.session.summary = summary

            msg = f"[dim]Resumed thread: {thread_id} ({len(loaded)} messages)[/]"
            if summary:
                msg += f"\n[dim]Summary: {summary[:100]}...[/]"
            return CommandResult(handled=True, message=msg)

        return CommandResult(
            handled=True,
            message=f"[dim]Thread not found: {thread_id}[/]",
        )

    def _list_sessions(self, ctx: CommandContext) -> CommandResult:
        """List saved sessions."""
        manager = get_session_manager()
        sessions = manager.list_sessions()

        if sessions:
            ctx.display.console.print("[bold]Saved sessions:[/]")
            for s in sessions:
                ctx.display.console.print(f"  {s['id']}: {s['message_count']} messages")
        else:
            ctx.display.console.print("[dim]No saved sessions.[/]")

        return CommandResult(handled=True)

    def _list_interrupted(self, ctx: CommandContext) -> CommandResult:
        """List interrupted sessions for checkpoint recovery."""
        manager = get_session_manager()
        interrupted = manager.list_interrupted_sessions()

        if interrupted:
            table = Table(title="Interrupted Sessions (Available for Recovery)")
            table.add_column("Session ID", style="cyan")
            table.add_column("Node", style="yellow")
            table.add_column("Iterations", style="white")
            table.add_column("Has Error", style="red")
            table.add_column("Updated", style="dim")

            for s in interrupted:
                table.add_row(
                    s["id"],
                    s["current_node"],
                    str(s["iteration_count"]),
                    "Yes" if s["has_error"] else "No",
                    s["updated_at"][:16] if s["updated_at"] else "N/A",
                )

            ctx.display.console.print(table)
            ctx.display.console.print("\n[dim]Use /resume <id> to recover a session[/]")
        else:
            ctx.display.console.print("[dim]No interrupted sessions found.[/]")

        return CommandResult(handled=True)

    def _reset_session(self, ctx: CommandContext) -> CommandResult:
        """Reset session history."""
        ctx.messages = []
        return CommandResult(
            handled=True,
            message="[dim]Conversation history cleared.[/]",
        )

    def _switch_thread(self, ctx: CommandContext, thread_id: str) -> CommandResult:
        """Switch to a different thread."""
        ctx.thread_id = thread_id
        ctx.messages = []
        return CommandResult(
            handled=True,
            message=f"[dim]Switched to thread: {thread_id}[/]",
        )

    def get_help_text(self) -> str:
        """Get help text for session commands."""
        return (
            "/reset - Clear conversation history\n"
            "/thread <id> - Switch to a new thread\n"
            "/resume <id> - Resume a saved thread (with checkpoint recovery)\n"
            "/interrupted - List interrupted sessions available for recovery\n"
            "/save [id] - Save current session\n"
            "/load <id> - Load a saved session\n"
            "/sessions - List saved sessions"
        )