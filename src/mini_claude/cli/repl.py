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


@bindings.add("s-tab")
def _(event):
    """Shift+Tab：循环切换权限模式（P3-2，对齐 Claude Code）。"""
    try:
        from ..permissions.manager import get_permission_manager
        from ..permissions.mode import describe

        mode = get_permission_manager().cycle_mode()
        # 在输入区上方给一行非侵入提示（append_to_buffer 不打断输入）
        event.app.invalidate()
        event.app.output.write(f"\r\n[mode] {mode.value} — {describe(mode)}\r\n")
        event.app.output.flush()
    except Exception as e:
        logger.debug("mode cycle failed", error=str(e))


# Custom style
style = Style.from_dict(
    {
        "prompt": "bold green",
        "": "#ffffff",
    }
)


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
        self._active_skill = None
        self._active_skill_args = ""
        # P4-1 /rewind：待分叉快照的 configurable（含 checkpoint_id），下轮用后即清
        self._rewind_configurable = None

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
        self._load_skills()

    def _load_skills(self):
        """Load skills from configured directories."""
        from ..skills.registry import get_skill_registry
        from mini_claude.config.settings import settings

        registry = get_skill_registry()
        try:
            from pathlib import Path

            user_dir = Path.home() / ".mini-claude" / "skills"
            project_dir = None
            if settings.workspace_root:
                project_dir = Path(settings.workspace_root) / "skills"

            count = registry.load(user_skills_dir=user_dir, project_skills_dir=project_dir)
            if count > 0:
                logger.debug(f"Loaded {count} skills")
        except Exception as e:
            logger.debug(f"Skills loading failed: {e}")

    def manage_history(self, messages: list, max_messages: int = 50) -> list:
        """Manage message history based on token count."""
        from mini_claude.config.settings import settings

        return manage_message_history(messages, max_messages, settings.default_model)

    async def _check_previous_session(self) -> bool:
        """Check if there's a previous session checkpoint in SQLite."""
        try:
            import aiosqlite
            from mini_claude.config.settings import settings

            db_path = settings.session_db_path
            async with aiosqlite.connect(db_path) as db:
                # Check if the checkpoints table exists and has data
                cursor = await db.execute(
                    "SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name='checkpoints'"
                )
                row = await cursor.fetchone()
                if row and row[0] > 0:
                    # P1-8：只看当前 thread 的 checkpoint，别人的会话不算我的。
                    # 旧逻辑全表 COUNT，有任何残留都弹恢复，新开 thread 也被误打扰。
                    try:
                        cursor = await db.execute(
                            "SELECT COUNT(*) FROM checkpoints WHERE thread_id = ?",
                            (self.thread_id,),
                        )
                        row = await cursor.fetchone()
                        return row and row[0] > 0
                    except Exception:
                        cursor = await db.execute("SELECT COUNT(*) FROM checkpoints")
                        row = await cursor.fetchone()
                        return row and row[0] > 0
        except Exception as e:
            logger.debug("session check failed", error=str(e))
        return False

    async def run_graph(self):
        """Run REPL with LangGraph state machine.

        退出清理放在 finally 里：/exit、Ctrl+D、Ctrl+C、asyncio.CancelledError
        以及未捕获异常都要走到。后台 bash 进程与 aiosqlite 的 worker 线程都不是
        daemon，漏清会让子进程变孤儿、或让解释器退出时挂住。
        """
        try:
            await self._run_graph_loop()
        finally:
            from ..agent.graph import close_checkpoint_connections
            from ..mcp.manager import close_mcp_connections
            from ..tools._http import close_shared_client
            from ..tools.bash import cleanup_all_background_processes, get_background_process_count

            if get_background_process_count() > 0:
                display.console.print("[dim]清理后台进程...[/]")
                await cleanup_all_background_processes()

            await close_checkpoint_connections()
            # MCP 连接同样非 daemon 级资源（stdio 子进程 + anyio 任务），
            # 漏关会挂解释器——与 checkpoint 同级的退出纪律。
            await close_mcp_connections()
            # 共享 httpx client（web 工具）连接收口——同一清理链
            await close_shared_client()

    async def _connect_mcp_servers(self):
        """启动时自动连接 mcp.json 配置的 server（失败逐个提示，不阻断）。"""
        from ..mcp.manager import auto_connect_on_startup

        try:
            connected, errors = await auto_connect_on_startup()
        except Exception as e:
            display.show_error(f"MCP 自动连接失败：{e}")
            return
        for name, err in errors.items():
            display.console.print(f"[yellow]MCP server {name} 连接失败：{err}[/]")
        if connected:
            display.console.print(f"[dim]MCP 已连接: {', '.join(connected)}[/]")

    async def _run_graph_loop(self):
        """REPL 主循环本体；资源清理由 run_graph 的 finally 统一负责。"""
        from ..agent.graph import get_agent_graph
        from mini_claude.config.settings import settings

        self.running = True
        display.welcome()

        # MCP 自动连接（P2）：配置了 mcp.json 就在启动时连接；失败不阻断主链路
        await self._connect_mcp_servers()

        # Check for previous session
        has_previous = await self._check_previous_session()
        if has_previous:
            try:
                choice = await self.session.prompt_async(
                    "\n发现上次未完成的会话，继续？[Y/n]: ", style=style
                )
                if choice.strip().lower() in ("", "y", "yes", "是"):
                    display.console.print("[dim]正在恢复会话...[/]")
                    # Continue with existing checkpoint - graph will auto-load state
                else:
                    # Start fresh - use a new thread_id to avoid loading old checkpoint
                    self.thread_id = f"thread_{int(__import__('time').time())}"
                    display.console.print("[dim]开始新会话[/]")
            except Exception as e:
                logger.debug("session recovery prompt failed", error=str(e))

        graph = get_agent_graph()

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
                        from ..utils.confirmations import route_confirmation_key
                        from ..utils.safety import approve_path

                        key = self.pending_confirmation_path
                        if not route_confirmation_key(key):
                            # 非前缀键 = 普通路径放行
                            approve_path(key)
                        display.console.print(f"[green]OK {key}[/]")
                        self.pending_confirmation_path = None
                        user_input = "请继续执行之前的任务"

                # Inject active skill if set
                effective_input = user_input
                if self._active_skill is not None:
                    skill = self._active_skill
                    args = self._active_skill_args
                    skill_context = f"\n\n[Skill: {skill.name}]\n{skill.body}\n[/Skill]"
                    if args:
                        skill_context += f"\n\nUser arguments: {args}"
                    effective_input = f"{user_input}{skill_context}"
                    self._active_skill = None
                    self._active_skill_args = ""

                # Process with LangGraph
                display.user_message(user_input)
                display._streamed = False  # Reset streaming flag each turn
                display.show_thinking()

                try:
                    # P4-1：每轮只传增量（新消息+本回合初始字段）。
                    # 历史（含 todos）由 checkpointer 携带——实测传全量历史会
                    # 把旧消息整段复制进 checkpoint（ISSUE-014 多轮版）。
                    # /rewind 时 config 带 checkpoint_id，从快照分叉重跑。
                    from ..agent.state import create_turn_increment

                    turn_state = create_turn_increment(effective_input, thread_id=self.thread_id)

                    configurable = {"thread_id": self.thread_id}
                    if self._rewind_configurable is not None:
                        configurable.update(self._rewind_configurable)
                        self._rewind_configurable = None

                    result = await graph.ainvoke(
                        turn_state,
                        config={
                            "configurable": configurable,
                            "recursion_limit": 50,
                        },
                    )

                    self._process_result(result)

                    if not display._streamed:
                        display.agent_message(self._get_response_text(result))

                    if settings.auto_save_enabled:
                        self._auto_save_session(settings)

                    # Stop hook（P3-1）：回合结束触发，只通知不阻断
                    try:
                        from ..hooks.dispatcher import get_hook_dispatcher

                        stop_reason = result.get("stop_reason")
                        reason = (
                            stop_reason.value if hasattr(stop_reason, "value") else "task_complete"
                        )
                        await get_hook_dispatcher().dispatch_stop(
                            reason=reason,
                            last_message=self._get_response_text(result),
                            thread_id=self.thread_id,
                        )
                    except Exception as stop_err:
                        logger.debug("stop hook failed", error=str(stop_err))

                except Exception as e:
                    from rich.markup import escape

                    from mini_claude.monitoring.health import classify_model_error

                    display.show_error(str(e))
                    # P1-7：LLM 失败给中文下一步，不只甩原文。
                    try:
                        hint = classify_model_error(str(e))
                        if hint:
                            display.console.print(f"[yellow]下一步：{escape(hint)}[/]")
                    except Exception:
                        pass

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
                self.messages.append({"role": "assistant", "content": msg.content or ""})
            # 其余（ToolMessage 等工具结果）：不进 REPL 展示历史（[Tool] 行由
            # act 回调实时显示），但保留在 checkpoint 里供 LLM 下一轮按协议使用

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
