"""REPL interactive mode.

This module provides the main REPL (Read-Eval-Print Loop) for Mini Claude Code.
Command handling is delegated to modular handlers in the commands package.
"""

from typing import Optional

from prompt_toolkit import PromptSession
from prompt_toolkit.history import FileHistory
from prompt_toolkit.auto_suggest import AutoSuggestFromHistory
from prompt_toolkit.styles import Style
from prompt_toolkit.key_binding import KeyBindings

from .display import display
from .repl_utils import manage_message_history
from ..utils.token_manager import count_messages_tokens
from ..utils.profile import UserProfileManager, UserProfile
from ..utils.logger import get_logger

logger = get_logger("mini_claude.cli.repl")


# Custom key bindings
bindings = KeyBindings()


@bindings.add("c-c")
def _(event):
    """Handle Ctrl+C."""
    event.app.exit(exception=KeyboardInterrupt, style="class:aborting")


@bindings.add("c-d")
def _(event):
    """Handle Ctrl+D."""
    event.app.exit(exception=EOFError, style="class:aborting")


# Custom style
style = Style.from_dict({
    "prompt": "bold green",
    "": "#ffffff",
})


class REPLSession:
    """REPL session manager.

    Attributes:
        session: PromptSession for user input
        history_file: Path to history file
        running: Whether the REPL is active
        messages: Conversation history
        thread_id: Thread ID for LangGraph checkpointer
        pending_confirmation_path: Path awaiting user confirmation
        summary: Session summary
        _profile_manager: Profile manager instance
        _profile: Cached user profile
        _execution_state: Execution state for checkpoint recovery
    """

    def __init__(self, history_file: str = ".mini_claude_history"):
        self.session: Optional[PromptSession] = None
        self.history_file = history_file
        self.running = False
        self.messages = []
        self.thread_id = "default"
        self.pending_confirmation_path: Optional[str] = None
        self.summary: Optional[str] = None
        self._profile_manager: Optional[UserProfileManager] = None
        self._profile: Optional[UserProfile] = None
        self._execution_state = None

    def _get_profile_manager(self) -> UserProfileManager:
        """Get or create profile manager."""
        if self._profile_manager is None:
            self._profile_manager = UserProfileManager()
        return self._profile_manager

    def _load_profile(self) -> UserProfile:
        """Load user profile on startup."""
        manager = self._get_profile_manager()
        self._profile = manager.load_profile()
        logger.debug("Profile loaded", model=self._profile.preferred_model)
        return self._profile

    def _save_profile(self) -> bool:
        """Save user profile on exit."""
        if self._profile is None:
            return False
        manager = self._get_profile_manager()
        result = manager.save_profile(self._profile)
        logger.debug("Profile saved", result=result)
        return result

    def initialize(self):
        """Initialize the REPL session."""
        self.session = PromptSession(
            history=FileHistory(self.history_file),
            auto_suggest=AutoSuggestFromHistory(),
            style=style,
            key_bindings=bindings,
            multiline=False,
        )
        self._load_profile()

    def manage_history(self, messages: list, max_messages: int = 50) -> list:
        """Manage message history based on token count."""
        from mini_claude.config.settings import settings
        return manage_message_history(
            messages, max_messages, settings.default_model
        )

    async def run_graph(self):
        """Run REPL with LangGraph state machine."""
        from ..agent.graph import get_agent_graph
        from ..agent.state import create_initial_state
        from ..llm.prompts import get_system_prompt
        from mini_claude.config.settings import settings

        self.running = True
        display.welcome()

        graph = get_agent_graph()
        provider = settings.get_model_provider()
        _ = get_system_prompt(provider)

        while self.running:
            try:
                user_input = await self.session.prompt_async("\n> ", style=style)

                if not user_input.strip():
                    continue

                # Handle commands
                if user_input.startswith("/"):
                    handled = await self._handle_command(user_input.strip())
                    if handled:
                        continue

                # Check for path confirmation response
                user_lower = user_input.strip().lower()
                if user_lower in ("yes", "y", "确认", "同意"):
                    if self.pending_confirmation_path:
                        from ..utils.safety import approve_path
                        approve_path(self.pending_confirmation_path)
                        display.console.print(
                            f"[green]OK {self.pending_confirmation_path}[/]"
                        )
                        self.pending_confirmation_path = None
                        user_input = "请继续执行之前的任务"

                # Process with LangGraph
                display.user_message(user_input)
                display.show_thinking()

                try:
                    from langchain_core.messages import HumanMessage, AIMessage

                    history_messages = self._build_history_messages()
                    initial_state = create_initial_state(user_input, history_messages)

                    result = await graph.ainvoke(
                        initial_state,
                        config={
                            "configurable": {"thread_id": self.thread_id},
                            "recursion_limit": 50,
                        }
                    )

                    self._process_result(result)

                    display.agent_message(self._get_response_text(result))

                    if settings.auto_save_enabled:
                        self._auto_save_session(settings)

                except Exception as e:
                    display.show_error(str(e))

            except KeyboardInterrupt:
                display.console.print("\n[dim]Interrupted. Press Ctrl+D to exit.[/]")
                continue
            except EOFError:
                display.console.print("\n[dim]Goodbye![/]")
                self.running = False
                self._save_profile()
                break
            except Exception as e:
                display.show_error(str(e))
                continue

    def _build_history_messages(self) -> list:
        """Build LangChain message list from history."""
        from langchain_core.messages import HumanMessage, AIMessage

        history_messages = []
        for msg in self.messages:
            if isinstance(msg, dict):
                role = msg.get("role", "user")
                content = msg.get("content", "")
                if role == "user":
                    history_messages.append(HumanMessage(content=content))
                elif role == "assistant":
                    history_messages.append(AIMessage(content=content))
            else:
                history_messages.append(msg)
        return history_messages

    def _process_result(self, result: dict) -> None:
        """Process graph result and update state."""
        from langchain_core.messages import HumanMessage, AIMessage

        messages = result.get("messages", [])
        self.pending_confirmation_path = result.get("pending_confirmation_path")

        self.messages = []
        for msg in messages:
            if isinstance(msg, HumanMessage):
                self.messages.append({"role": "user", "content": msg.content})
            elif isinstance(msg, AIMessage):
                self.messages.append({
                    "role": "assistant",
                    "content": msg.content or ""
                })

        self.messages = self.manage_history(self.messages)

    def _get_response_text(self, result: dict) -> str:
        """Extract response text from result."""
        messages = result.get("messages", [])
        if messages:
            last_message = messages[-1]
            return last_message.content if hasattr(last_message, "content") else str(last_message)
        return "抱歉，我无法处理这个请求。"

    def _auto_save_session(self, settings) -> None:
        """Auto-save session if enabled."""
        from ..utils.session import get_session_manager

        manager = get_session_manager(settings.session_db_path)
        manager.save_session(self.thread_id, self.messages)

    async def _handle_command(self, command: str) -> bool:
        """Handle slash commands.

        Delegates to command handlers in the commands package.

        Args:
            command: The command string (e.g., "/help")

        Returns:
            True if command was handled
        """
        from .commands import dispatch_command
        return await dispatch_command(self, command, display)
