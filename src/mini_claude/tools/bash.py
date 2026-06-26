"""Command execution tools."""

import asyncio
from typing import Dict, Any

from .base import BaseTool, register_tool
from ..utils.safety import validate_command

# Track background processes for cleanup
_background_processes: Dict[str, asyncio.subprocess.Process] = {}


def _cleanup_finished_processes() -> None:
    """Remove finished processes from tracking dict and consume their pipes."""
    finished = [
        tid for tid, proc in _background_processes.items()
        if proc.returncode is not None
    ]
    for tid in finished:
        proc = _background_processes.pop(tid, None)
        if proc and proc.returncode is not None:
            # Consume remaining pipe data to prevent blocking
            try:
                proc.stdout and proc.stdout.read_nowait()
            except (asyncio.LimitOverrunError, ValueError):
                pass
            try:
                proc.stderr and proc.stderr.read_nowait()
            except (asyncio.LimitOverrunError, ValueError):
                pass


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
            return f"Error executing command: {e}"


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
            process = await asyncio.create_subprocess_shell(
                command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )

            # Track process for cleanup
            task_id = f"task_{process.pid}"
            _background_processes[task_id] = process

            # Clean up finished processes
            _cleanup_finished_processes()

            return f"Started background task: {task_id}\nPID: {process.pid}"

        except Exception as e:
            return f"Error starting background task: {e}"


# Register command tools
register_tool(RunCommandTool())
register_tool(RunBackgroundTool())
