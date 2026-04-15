"""Command execution tools."""

import asyncio
import subprocess
from typing import Dict, Any, Optional

from .base import BaseTool, register_tool
from ..utils.safety import validate_command, SafetyChecker


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
                stdout, stderr = await asyncio.wait_for(
                    process.communicate(),
                    timeout=timeout
                )
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

            # Store process for later retrieval
            task_id = f"task_{id(process)}"

            return f"Started background task: {task_id}\nPID: {process.pid}"

        except Exception as e:
            return f"Error starting background task: {e}"


# Register command tools
register_tool(RunCommandTool())
register_tool(RunBackgroundTool())
