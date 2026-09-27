"""Command execution tools."""

import asyncio
import os
import tempfile
from typing import Dict, Any

from .base import BaseTool, register_tool
from ..utils.logger import get_logger
from ..utils.safety import validate_command

logger = get_logger("mini_claude.tools.bash")

# Track background processes for cleanup
_background_processes: Dict[str, asyncio.subprocess.Process] = {}
# P4-2：后台任务输出重定向文件（替代 PIPE——PIPE 写满会卡死子进程）
_background_outputs: Dict[str, str] = {}


def _cleanup_finished_processes() -> None:
    """Remove finished processes from tracking dict and consume their pipes."""
    finished = [tid for tid, proc in _background_processes.items() if proc.returncode is not None]
    for tid in finished:
        _background_processes.pop(tid, None)


async def cleanup_all_background_processes() -> None:
    """Kill and clean up all tracked background processes."""
    for tid, proc in list(_background_processes.items()):
        if proc.returncode is None:
            try:
                proc.kill()
                await proc.wait()
            except ProcessLookupError:
                pass
    _background_processes.clear()


class RunCommandTool(BaseTool):
    """Execute a shell command."""

    @property
    def name(self) -> str:
        return "run_command"

    @property
    def description(self) -> str:
        return "[LAST RESORT] Execute a shell command. Only use when no other tool is suitable. Prefer read_file, write_file, edit_file, list_dir, search_files for file operations."

    @property
    def parameters(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "command": {
                    "type": "string",
                    "description": "Shell command to execute",
                },
                "timeout": {
                    "type": "integer",
                    "description": "Timeout in seconds (default: 30)",
                },
            },
            "required": ["command"],
        }

    @property
    def examples(self) -> list:
        return [
            {
                "description": "List files with details (prefer list_dir tool instead)",
                "input": {"command": "ls -la"},
                "expected_output": "Exit code: 0\ntotal 24\ndrwxr-xr-x 2 user user 4096...",
            },
            {
                "description": "Run Python script",
                "input": {"command": "python script.py", "timeout": 60},
                "expected_output": "Exit code: 0\nScript output here...",
            },
            {
                "description": "Check git status",
                "input": {"command": "git status"},
                "expected_output": "Exit code: 0\nOn branch main\nnothing to commit...",
            },
        ]

    async def execute(self, command: str, timeout: int = 30) -> str:
        # Validate command
        is_safe, reason = validate_command(command)
        if not is_safe:
            return f"Error: {reason}"

        try:
            process = await asyncio.create_subprocess_shell(
                command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )

            try:
                stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=timeout)
            except asyncio.TimeoutError:
                process.kill()
                return f"Error: Command timed out after {timeout} seconds"

            output = []
            if stdout:
                output.append(stdout.decode("utf-8", errors="replace"))
            if stderr:
                output.append(f"STDERR:\n{stderr.decode('utf-8', errors='replace')}")

            result = "\n".join(output) or "(no output)"
            return f"Exit code: {process.returncode}\n{result}"

        except Exception as e:
            return f"Error executing command: {type(e).__name__}"


class RunBackgroundTool(BaseTool):
    """Execute a command in the background."""

    @property
    def name(self) -> str:
        return "run_background"

    @property
    def description(self) -> str:
        return "Execute a command in the background and return a task ID"

    @property
    def parameters(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "command": {
                    "type": "string",
                    "description": "Shell command to execute in background",
                },
            },
            "required": ["command"],
        }

    async def execute(self, command: str) -> str:
        # Validate command
        is_safe, reason = validate_command(command)
        if not is_safe:
            return f"Error: {reason}"

        try:
            # P4-2：输出重定向到文件。PIPE 写满会卡死子进程（无人消费），
            # 文件输出同时让 task_output 可以随时读（对齐 BashOutput）。
            task_id = f"task_{len(_background_processes) + 1}_{os.getpid()}"
            out_path = os.path.join(tempfile.gettempdir(), f"mini_claude_{task_id}.out")
            out_fd = os.open(out_path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC)
            env = dict(os.environ)
            env.update(
                {"PYTHONUTF8": "1", "PYTHONIOENCODING": "utf-8:replace", "PYTHONUNBUFFERED": "1"}
            )

            process = await asyncio.create_subprocess_shell(
                command,
                stdout=out_fd,
                stderr=asyncio.subprocess.STDOUT,
                env=env,
            )
            os.close(out_fd)

            # Track process for cleanup
            _background_processes[task_id] = process
            _background_outputs[task_id] = out_path

            # Clean up finished processes
            _cleanup_finished_processes()

            return (
                f"Started background task: {task_id}\nPID: {process.pid}\nOutput file: {out_path}"
            )

        except Exception as e:
            # ISSUE-012 #6：与 RunCommandTool:119 对齐，只报类型名，不回显内部详情。
            return f"Error starting background task: {type(e).__name__}"


def get_background_process_count() -> int:
    """Return the number of tracked background processes."""
    _cleanup_finished_processes()
    return len(_background_processes)


class TaskOutputTool(BaseTool):
    """Read output of a background task (P4-2, 对齐 BashOutput)."""

    @property
    def name(self) -> str:
        return "task_output"

    @property
    def description(self) -> str:
        return (
            "Read the current output of a background task started by run_background. "
            "Use task_id from run_background's result. Unknown ids list available ones."
        )

    @property
    def parameters(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "task_id": {"type": "string", "description": "Background task id"},
                "tail_bytes": {
                    "type": "integer",
                    "description": "Only read the last N bytes (default 4000)",
                    "default": 4000,
                },
            },
            "required": ["task_id"],
        }

    async def execute(self, task_id: str, tail_bytes: int = 4000) -> str:
        out_path = _background_outputs.get(task_id)
        proc = _background_processes.get(task_id)
        if out_path is None:
            available = ", ".join(_background_outputs) or "(none)"
            return f"Error: 未知后台任务 {task_id!r}。可用任务: {available}"

        try:
            with open(out_path, "rb") as f:
                f.seek(0, os.SEEK_END)
                size = f.tell()
                f.seek(max(0, size - max(int(tail_bytes), 100)))
                data = f.read()
        except OSError as e:
            return f"Error: 读取输出文件失败：{type(e).__name__}: {e}"

        text = data.decode("utf-8", errors="replace")
        running = proc is not None and proc.returncode is None
        header = (
            f"Task {task_id} status: running"
            if running
            else f"Task {task_id} status: finished, Exit code: {proc.returncode if proc else '?'}"
        )
        body = text or "(尚无输出)"
        return f"{header}\n{body}"


class TaskKillTool(BaseTool):
    """Terminate a background task (P4-2, 对齐 KillShell)."""

    @property
    def name(self) -> str:
        return "task_kill"

    @property
    def description(self) -> str:
        return "Kill a background task started by run_background. Use its task_id."

    @property
    def parameters(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {"task_id": {"type": "string", "description": "Background task id"}},
            "required": ["task_id"],
        }

    async def execute(self, task_id: str) -> str:
        proc = _background_processes.get(task_id)
        if proc is None:
            available = ", ".join(_background_processes) or "(none)"
            return f"Error: 未知后台任务 {task_id!r}。可用任务: {available}"
        if proc.returncode is not None:
            return f"Task {task_id} 已结束（exit code {proc.returncode}）"
        try:
            proc.kill()
            await proc.wait()
        except ProcessLookupError:
            pass
        except Exception as e:
            return f"Error: 终止失败：{type(e).__name__}: {e}"
        logger.info("background task killed", task_id=task_id)
        return f"Task {task_id} 已终止。"


# Register command tools


# Register command tools
register_tool(RunCommandTool())
register_tool(RunBackgroundTool())
register_tool(TaskOutputTool())
register_tool(TaskKillTool())
