"""Rich output formatting for CLI."""

import sys
import io
from typing import Dict, List
from enum import Enum

from rich.console import Console
from rich.panel import Panel
from rich.markdown import Markdown
from rich.syntax import Syntax
from rich.table import Table


class AgentStatus(Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class SuggestionDisplay:
    """Display suggestions using Rich panels."""

    def __init__(self, console: Console):
        self.console = console

    def show_suggestion(self, suggestion) -> None:
        """Display a single suggestion with Rich Panel.

        Args:
            suggestion: Suggestion object from suggestion module
        """
        # Import here to avoid circular dependency
        from ..agent.suggestion import Priority

        # Determine color based on priority
        color_map = {
            Priority.HIGH: "red",
            Priority.MEDIUM: "yellow",
            Priority.LOW: "blue",
        }
        color = color_map.get(suggestion.priority, "white")

        # Build content
        lines = [suggestion.description, ""]

        if suggestion.actions:
            lines.append("[bold]Suggested Actions:[/]")
            for i, action in enumerate(suggestion.actions, 1):
                lines.append(f"  {i}. {action}")
            lines.append("")

        if suggestion.command:
            lines.append(f"[bold]Quick Command:[/] [cyan]{suggestion.command}[/]")

        if suggestion.doc_link:
            lines.append(f"[bold]Documentation:[/] [link={suggestion.doc_link}]{suggestion.doc_link}[/]")

        content = "\n".join(lines)

        # Create panel with priority-based styling
        self.console.print(Panel(
            content,
            title=f"[bold {color}]💡 {suggestion.title}[/]",
            border_style=color,
            padding=(1, 2),
        ))

    def show_suggestions(self, suggestions: List, title: str = "Suggestions") -> None:
        """Display multiple suggestions.

        Args:
            suggestions: List of Suggestion objects
            title: Panel title
        """
        if not suggestions:
            return

        self.console.print(f"\n[bold]{title}:[/]")
        for suggestion in suggestions:
            self.show_suggestion(suggestion)


class AgentDisplay:
    """Rich-based display for agent interactions."""

    def __init__(self):
        # Force UTF-8 encoding for Windows (skip in test environment)
        if sys.platform == "win32" and "pytest" not in sys.modules:
            sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
            sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")
        self.console = Console()
        self._streaming_text = ""
        self._is_streaming = False
        self._suggestion_display = SuggestionDisplay(self.console)

    def welcome(self):
        """Display welcome message."""
        self.console.print(Panel.fit(
            "[bold blue]Mini Claude Code[/]\n"
            "[dim]A multi-agent CLI assistant[/]\n\n"
            "[dim]Type your request or /help for commands[/]",
            border_style="blue",
        ))

    def user_message(self, message: str):
        """Display user message."""
        self.console.print(f"\n[bold green]You:[/] {message}")

    def agent_message(self, message: str):
        """Display agent response."""
        self.console.print("\n[bold blue]Assistant:[/]")
        # Try to render as markdown if it looks like markdown
        if any(marker in message for marker in ["```", "##", "**", "- "]):
            self.console.print(Markdown(message))
        else:
            self.console.print(message)

    def start_stream(self):
        """Start streaming output."""
        self._streaming_text = ""
        self._is_streaming = True
        self.console.print("\n[bold blue]Assistant:[/] ", end="")

    def stream_token(self, token: str):
        """Stream a single token."""
        if not self._is_streaming:
            self.start_stream()
        self._streaming_text += token
        # Print token directly (no formatting during stream)
        print(token, end="", flush=True)

    def end_stream(self):
        """End streaming output."""
        if self._is_streaming:
            print()  # New line after streaming
            self._is_streaming = False
            # Don't re-render - content was already printed during streaming
            # This avoids duplicate output

    def show_tool_call_start(self, tool_name: str):
        """Display tool call start (for streaming)."""
        self._streaming_text = ""
        self._is_streaming = True
        self._current_tool = tool_name
        # Use sys.stdout for immediate output on Windows
        sys.stdout.write(f"\n[tool] {tool_name}(")
        sys.stdout.flush()

    def stream_tool_args(self, args_chunk: str):
        """Stream tool arguments (code content)."""
        sys.stdout.write(args_chunk)
        sys.stdout.flush()

    def show_tool_call(self, tool_name: str, params: dict):
        """Display tool call."""
        params_str = ", ".join(f"{k}={v!r}" for k, v in params.items())
        self.console.print(f"\n[dim][tool] Calling: [bold]{tool_name}[/]({params_str})[/]")

    def show_tool_result(self, result: str, success: bool = True):
        """Display tool result."""
        color = "green" if success else "red"
        self.console.print(f"[dim {color}]Result: {result[:200]}{'...' if len(result) > 200 else ''}[/]")

    def show_info(self, message: str):
        """Display informational message."""
        self.console.print(f"[dim cyan]{message}[/]")

    def show_plan(self, plan: List[str]):
        """Display execution plan."""
        self.console.print("\n[bold][Plan] Execution Plan:[/]")
        for i, step in enumerate(plan, 1):
            self.console.print(f"  [cyan]{i}.[/] {step}")

    def show_sub_agents(self, agents: Dict[str, dict]):
        """Display sub-agent status panel."""
        if not agents:
            return

        table = Table(title="Sub-Agents Status")
        table.add_column("Agent", style="cyan")
        table.add_column("Status", style="magenta")
        table.add_column("Progress", style="green")

        for agent_id, info in agents.items():
            status = info.get("status", "unknown")
            progress = info.get("progress", 0)

            status_style = {
                "running": "[yellow]Running[/]",
                "completed": "[green]Completed[/]",
                "failed": "[red]Failed[/]",
                "pending": "[dim]Pending[/]",
            }.get(status, status)

            table.add_row(agent_id, status_style, f"{progress*100:.0f}%")

        self.console.print(table)

    def show_code(self, code: str, language: str = "python"):
        """Display code block with syntax highlighting."""
        syntax = Syntax(code, language, theme="monokai", line_numbers=True)
        self.console.print(syntax)

    def show_error(self, error: str):
        """Display error message."""
        self.console.print(f"\n[bold red]Error:[/] {error}")

    def show_thinking(self, message: str = "Thinking..."):
        """Show thinking indicator."""
        self.console.print(f"\n[dim yellow][*] {message}[/]")

    def show_success(self, message: str):
        """Display success message."""
        self.console.print(f"\n[bold green][OK][/]{message}")

    def confirm(self, message: str) -> bool:
        """Ask for user confirmation."""
        from rich.prompt import Confirm
        return Confirm.ask(message)

    def prompt(self, message: str = "> ") -> str:
        """Prompt for user input."""
        from rich.prompt import Prompt
        return Prompt.ask(message)

    def show_suggestion(self, suggestion) -> None:
        """Display a suggestion with Rich Panel.

        Args:
            suggestion: Suggestion object from suggestion module
        """
        self._suggestion_display.show_suggestion(suggestion)

    def show_suggestions(self, suggestions: List, title: str = "Suggestions") -> None:
        """Display multiple suggestions.

        Args:
            suggestions: List of Suggestion objects
            title: Panel title
        """
        self._suggestion_display.show_suggestions(suggestions, title)


# Global display instance
display = AgentDisplay()
