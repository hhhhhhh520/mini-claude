"""Rich output formatting for CLI."""

import sys
import io
from typing import Dict, List, Optional
from enum import Enum

from rich.console import Console
from rich.panel import Panel
from rich.markdown import Markdown
from rich.syntax import Syntax
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.live import Live
from rich.table import Table
from rich.text import Text


class AgentStatus(Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class AgentDisplay:
    """Rich-based display for agent interactions."""

    def __init__(self):
        # Force UTF-8 encoding for Windows
        if sys.platform == "win32":
            sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
            sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")
        self.console = Console()
        self._streaming_text = ""
        self._is_streaming = False

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
        self.console.print(f"\n[bold blue]Assistant:[/]")
        # Try to render as markdown if it looks like markdown
        if any(marker in message for marker in ["```", "##", "**", "- "]):
            self.console.print(Markdown(message))
        else:
            self.console.print(message)

    def start_stream(self):
        """Start streaming output."""
        self._streaming_text = ""
        self._is_streaming = True
        self.console.print(f"\n[bold blue]Assistant:[/] ", end="")

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
            # Optionally re-render as markdown for better display
            if any(marker in self._streaming_text for marker in ["```", "##", "**", "- "]):
                self.console.print("\n")  # Add spacing
                # Clear and re-render as markdown
                self.console.print(Markdown(self._streaming_text))

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


# Global display instance
display = AgentDisplay()
