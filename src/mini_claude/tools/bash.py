"""Command execution tools."""

import asyncio
import os
import tempfile
from typing import Any, Dict, List, Optional

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


# ---- 会话级 cwd 持久化（收敛批次③D） ----
# 诚实边界：持久的是**工作目录**（cd 跨调用生效），env 变量不持久
# （本体的 shell snapshot 机制未做）。实现为"cd 前缀 + 哨兵捕获"而非
# 持久进程：每条命令在会话 cwd 里起跑，结束后取回最终 cwd。
_session_cwd: Optional[str] = None
_CWD_SENTINEL = "__MC_CWD__"

# ---- 会话级 env 持久化（收敛批次④A） ----
# 只捕获**显式** `export K=V`（POSIX）/ `set K=V`（cmd）——脚本/子进程里
# 的 export 对会话不可见（诚实边界，与 cwd 同级）。注入顺序：先 env 后 cd。
_session_env: Dict[str, str] = {}


def get_session_env() -> Dict[str, str]:
    return dict(_session_env)


def set_session_env(env: Dict[str, str]) -> None:
    global _session_env
    _session_env = dict(env or {})


def reset_session_env() -> None:
    _session_env.clear()


def _parse_env_assignments(command: str) -> Dict[str, str]:
    """从命令里解析显式的 export K=V / set K=V 赋值（尽力而为）。

    只认单行内的直接赋值：POSIX `export K=V [K2=V2 ...]`（shlex 分词，
    引号内空格保留）；cmd `set K=V...`（行内其余部分整体为值，剥一层引号）。
    """
    import re
    import shlex

    out: Dict[str, str] = {}
    name_re = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")

    if os.name != "nt":
        for line in command.splitlines():
            stripped = line.strip()
            if not stripped.startswith("export "):
                continue
            try:
                tokens = shlex.split(stripped)[1:]
            except ValueError:
                continue
            for token in tokens:
                if "=" in token:
                    key, _, value = token.partition("=")
                    if name_re.match(key):
                        out[key] = value
    else:
        for line in command.splitlines():
            m = re.match(r'^\s*set\s+"?([A-Za-z_][A-Za-z0-9_]*)=(.*)"?$', line, re.IGNORECASE)
            if m:
                key, value = m.group(1), m.group(2).strip()
                if value.endswith('"'):
                    value = value[:-1]
                if name_re.match(key):
                    out[key] = value
    return out


def get_session_cwd() -> Optional[str]:
    return _session_cwd


def set_session_cwd(path: Optional[str]) -> None:
    global _session_cwd
    _session_cwd = path


def _cd_prefix() -> str:
    """回到会话 cwd 的命令前缀（cmd 用 /d 跨盘；sh 用引号）。"""
    if not _session_cwd:
        return ""
    if os.name == "nt":
        return f'cd /d "{_session_cwd}" & '
    return f'cd "{_session_cwd}" && '


def _wrap_cwd_capture(command: str) -> str:
    """命令后追加取 cwd 的收尾命令。

    平台分治（两个 shell 展开时机的坑都实测踩过）：
    - Windows：不能用 `%CD%`——它在**整行解析时**展开，拿到的是 cd 之前的
      老目录；也不能用换行——cmd /c 遇到内嵌换行只执行第一行。改为把
      `cd`（无参，**执行时**打印当前目录）重定向到临时文件。
    - POSIX：`$PWD` 在该段命令执行时展开，`;` 串联即可。
    """
    if os.name == "nt":
        cwd_file = os.path.join(tempfile.gettempdir(), f"mini_claude_cwd_{os.getpid()}.tmp")
        return f'{command} & cd>"{cwd_file}"'
    return f"{command}; echo {_CWD_SENTINEL}$PWD"


def _read_cwd_file() -> Optional[str]:
    """读取并删除 Windows 侧的 cwd 临时文件（尽力而为）。"""
    cwd_file = os.path.join(tempfile.gettempdir(), f"mini_claude_cwd_{os.getpid()}.tmp")
    try:
        with open(cwd_file, "r", encoding="utf-8", errors="replace") as f:
            content = f.read().strip()
        os.remove(cwd_file)
        return content or None
    except OSError:
        return None


def _extract_cwd(output: str) -> Optional[str]:
    """从输出末尾解析哨兵行；没有（超时被杀等）返回 None（cwd 不变）。"""
    cwd = None
    lines = output.splitlines()
    keep: List[str] = []
    for line in lines:
        if line.startswith(_CWD_SENTINEL):
            candidate = line[len(_CWD_SENTINEL) :].strip()
            if candidate:
                cwd = candidate
            continue  # 哨兵行从输出剔除
        keep.append(line)
    if cwd is not None:
        set_session_cwd(cwd)
        return "\n".join(keep)
    return None


class RunCommandTool(BaseTool):
    """Execute a shell command."""

    @property
    def name(self) -> str:
        return "run_command"

    @property
    def description(self) -> str:
        return (
            "[LAST RESORT] Execute a shell command. Only use when no other tool is "
            "suitable. Prefer read_file, write_file, edit_file, list_dir, "
            "search_files for file operations. The working directory persists "
            "across calls: `cd` in one command carries into the next (env vars "
            "do not persist)."
        )

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

        # 收敛批次③D：会话 cwd 前缀 + 结束后取最终工作目录
        # 收敛批次④A：显式 export/set 记进会话 env，经子进程 env 注入——
        # 不能用 set 前缀：cmd 的 %VAR% 在整行解析期展开，同行 set 完拿不到
        _session_env.update(_parse_env_assignments(command))
        command = _cd_prefix() + command
        command = _wrap_cwd_capture(command)

        try:
            process = await asyncio.create_subprocess_shell(
                command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env={**os.environ, **_session_env},
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
            if os.name == "nt":
                # Windows：cwd 经临时文件回传（%CD% 的解析期展开坑见
                # _wrap_cwd_capture docstring）；输出本身无哨兵行，无需剔除
                new_cwd = _read_cwd_file()
                if new_cwd:
                    set_session_cwd(new_cwd)
            else:
                stripped = _extract_cwd(result)
                if stripped is not None:
                    result = stripped
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

        # 收敛批次③D：后台命令同样从会话 cwd 起跑（不捕获——进程长驻）
        # 收敛批次④A：显式 export/set 记进会话 env，经子进程 env 注入——
        # 不能用 set 前缀：cmd 的 %VAR% 在整行解析期展开，同行 set 完拿不到
        _session_env.update(_parse_env_assignments(command))
        command = _cd_prefix() + command

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
            env.update(_session_env)

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
