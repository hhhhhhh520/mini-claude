"""REPL interactive mode."""

import asyncio
from typing import Optional

from prompt_toolkit import PromptSession
from prompt_toolkit.history import FileHistory
from prompt_toolkit.auto_suggest import AutoSuggestFromHistory
from prompt_toolkit.styles import Style
from prompt_toolkit.key_binding import KeyBindings

from .display import display


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
    """REPL session manager."""

    def __init__(self, history_file: str = ".mini_claude_history"):
        self.session: Optional[PromptSession] = None
        self.history_file = history_file
        self.running = False
        self.messages = []
        self.thread_id = "default"  # Thread ID for LangGraph checkpointer

    def initialize(self):
        """Initialize the REPL session."""
        self.session = PromptSession(
            history=FileHistory(self.history_file),
            auto_suggest=AutoSuggestFromHistory(),
            style=style,
            key_bindings=bindings,
            multiline=False,  # 单次回车提交
        )

    async def run_graph(self):
        """Run REPL with LangGraph state machine."""
        from ..agent.graph import get_agent_graph
        from ..agent.state import create_initial_state
        from ..llm.prompts import get_system_prompt
        from mini_claude.config.settings import settings, ModelProvider

        self.running = True
        display.welcome()

        graph = get_agent_graph()
        provider = settings.get_model_provider()
        system_prompt = get_system_prompt(provider)

        while self.running:
            try:
                # Get user input
                user_input = await self.session.prompt_async(
                    "\n> ",
                    style=style,
                )

                if not user_input.strip():
                    continue

                # Handle commands
                if user_input.startswith("/"):
                    handled = await self._handle_command(user_input.strip())
                    if handled:
                        continue

                # Process with LangGraph
                display.user_message(user_input)
                display.show_thinking()

                try:
                    # Build messages from history
                    from langchain_core.messages import HumanMessage, AIMessage, SystemMessage

                    # Convert history to LangChain messages
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

                    # Create initial state with history
                    initial_state = create_initial_state(user_input, history_messages)

                    # Run the graph with thread_id for checkpointer
                    result = await graph.ainvoke(
                        initial_state,
                        config={
                            "configurable": {"thread_id": self.thread_id},
                            "recursion_limit": 50
                        }
                    )

                    # Extract final response
                    messages = result.get("messages", [])
                    if messages:
                        last_message = messages[-1]
                        response_text = last_message.content if hasattr(last_message, 'content') else str(last_message)
                    else:
                        response_text = "抱歉，我无法处理这个请求。"

                    # Update history (keep last 20 messages, convert to dict for storage)
                    self.messages = []
                    for msg in messages[-20:]:
                        if isinstance(msg, HumanMessage):
                            self.messages.append({"role": "user", "content": msg.content})
                        elif isinstance(msg, AIMessage):
                            self.messages.append({"role": "assistant", "content": msg.content or ""})

                    display.agent_message(response_text)

                    # Auto-save if enabled
                    if settings.auto_save_enabled:
                        from ..utils.session import get_session_manager
                        manager = get_session_manager(settings.session_db_path)
                        manager.save_session(self.thread_id, self.messages)

                except Exception as e:
                    display.show_error(str(e))

            except KeyboardInterrupt:
                display.console.print("\n[dim]Interrupted. Press Ctrl+D to exit.[/]")
                continue
            except EOFError:
                display.console.print("\n[dim]Goodbye![/]")
                self.running = False
                break
            except Exception as e:
                display.show_error(str(e))
                continue

    async def run_simple(self):
        """Run a simple REPL loop with tool support."""
        import json
        from ..llm.provider import LLMProvider, convert_tools_to_litellm
        from ..llm.prompts import get_system_prompt
        from ..tools import get_all_tools, execute_tool
        from mini_claude.config.settings import settings, ModelProvider

        self.running = True
        display.welcome()

        llm = LLMProvider()
        provider = settings.get_model_provider()
        system_prompt = get_system_prompt(provider)
        tools = get_all_tools()
        litellm_tools = convert_tools_to_litellm(tools)

        while self.running:
            try:
                # Get user input
                user_input = await self.session.prompt_async(
                    "\n> ",
                    style=style,
                )

                if not user_input.strip():
                    continue

                # Handle commands
                if user_input.startswith("/"):
                    handled = await self._handle_command(user_input.strip())
                    if handled:
                        continue

                # Process with LLM
                display.user_message(user_input)
                display.show_thinking()

                # Build messages
                messages = [{"role": "system", "content": system_prompt}]
                messages.extend(self.messages)
                messages.append({"role": "user", "content": user_input})

                try:
                    # First call with tools
                    response = await llm.chat(
                        messages=messages,
                        tools=litellm_tools,
                        tool_choice="auto",
                    )

                    message = response.choices[0].message

                    # Check for tool calls
                    if hasattr(message, "tool_calls") and message.tool_calls:
                        # Execute tools
                        for tc in message.tool_calls:
                            tool_name = tc.function.name
                            tool_args = tc.function.arguments

                            if isinstance(tool_args, str):
                                tool_args = json.loads(tool_args)

                            print(f"[Tool] {tool_name}({tool_args})")
                            result = await execute_tool(tool_name, tool_args)

                            # Add assistant message and tool result
                            messages.append({"role": "assistant", "content": message.content or ""})
                            messages.append({"role": "user", "content": f"Tool {tool_name} result: {result}"})

                        # Second call to process tool results
                        response = await llm.chat(messages=messages)
                        result_text = response.choices[0].message.content
                    else:
                        result_text = message.content or ""

                    # Update history
                    self.messages.append({"role": "user", "content": user_input})
                    self.messages.append({"role": "assistant", "content": result_text})

                    # Keep only last 20 messages
                    if len(self.messages) > 20:
                        self.messages = self.messages[-20:]

                    display.agent_message(result_text)

                except Exception as e:
                    display.show_error(str(e))

            except KeyboardInterrupt:
                display.console.print("\n[dim]Interrupted. Press Ctrl+D to exit.[/]")
                continue
            except EOFError:
                display.console.print("\n[dim]Goodbye![/]")
                self.running = False
                break
            except Exception as e:
                display.show_error(str(e))
                continue

    async def _handle_command(self, command: str) -> bool:
        """Handle slash commands. Returns True if handled."""
        cmd = command.lower()

        if cmd in ("/exit", "/quit", "/q"):
            display.console.print("[dim]Goodbye![/]")
            self.running = False
            return True

        elif cmd == "/help":
            display.console.print(Panel.fit(
                "[bold]Commands:[/]\n"
                "/help - Show this help\n"
                "/exit, /quit, /q - Exit REPL\n"
                "/clear - Clear screen\n"
                "/model <name> - Switch model\n"
                "/status - Show session status\n"
                "/reset - Clear conversation history\n"
                "/thread <id> - Switch to a new thread\n"
                "/resume <id> - Resume a saved thread\n"
                "/save [id] - Save current session\n"
                "/load <id> - Load a saved session\n"
                "/sessions - List saved sessions",
                title="Help",
            ))
            return True

        elif cmd == "/clear":
            display.console.clear()
            return True

        elif cmd == "/reset":
            self.messages = []
            display.console.print("[dim]Conversation history cleared.[/]")
            return True

        elif cmd.startswith("/model "):
            model = command[7:].strip()
            display.console.print(f"[dim]Model switched to: {model}[/]")
            return True

        elif cmd == "/status":
            display.console.print(f"[dim]Messages in history: {len(self.messages)}[/]")
            display.console.print(f"[dim]Thread ID: {self.thread_id}[/]")
            return True

        elif cmd.startswith("/thread "):
            # Switch to a different thread
            self.thread_id = command[8:].strip()
            self.messages = []  # Clear current messages
            display.console.print(f"[dim]Switched to thread: {self.thread_id}[/]")
            return True

        elif cmd.startswith("/resume "):
            # Resume a previous thread from session storage
            from ..utils.session import get_session_manager
            thread_id = command[8:].strip()
            manager = get_session_manager()
            loaded = manager.load_session(thread_id)
            if loaded:
                self.messages = loaded
                self.thread_id = thread_id
                display.console.print(f"[dim]Resumed thread: {thread_id} ({len(loaded)} messages)[/]")

        elif cmd.startswith("/save"):
            from ..utils.session import get_session_manager
            session_id = command[5:].strip() or "default"
            manager = get_session_manager()
            manager.save_session(session_id, self.messages)
            display.console.print(f"[dim]Session saved as: {session_id}[/]")
            return True

        elif cmd.startswith("/load "):
            from ..utils.session import get_session_manager
            session_id = command[6:].strip()
            manager = get_session_manager()
            loaded = manager.load_session(session_id)
            if loaded:
                self.messages = loaded
                display.console.print(f"[dim]Session loaded: {session_id} ({len(loaded)} messages)[/]")
            else:
                display.console.print(f"[dim]Session not found: {session_id}[/]")
            return True

        elif cmd == "/sessions":
            from ..utils.session import get_session_manager
            manager = get_session_manager()
            sessions = manager.list_sessions()
            if sessions:
                display.console.print("[bold]Saved sessions:[/]")
                for s in sessions:
                    display.console.print(f"  {s['id']}: {s['message_count']} messages")
            else:
                display.console.print("[dim]No saved sessions.[/]")
            return True

        return False
