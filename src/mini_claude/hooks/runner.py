"""hook 命令执行器（P3-1）。

用户自配的受信命令，经 shell 执行：JSON payload 走 stdin，
exit code / stdout / stderr 回传。超时强杀（复用"非 daemon 子进程必须收尸"纪律）。

子进程强制 UTF-8（PYTHONUTF8/PYTHONIOENCODING）：Windows CI 的子进程默认继承
cp1252，hook 脚本打印中文会 UnicodeEncodeError 崩溃（实测踩中，见 PROGRESS P3）。
"""

import asyncio
import json
import os
from dataclasses import dataclass
from typing import Dict, Optional

from ..utils.logger import get_logger

logger = get_logger("mini_claude.hooks.runner")

# 给子进程的 UTF-8 保险：Python 脚本类的 hook 在任意 Windows 代码页下都能打中文
_CHILD_UTF8_ENV = {
    "PYTHONUTF8": "1",
    "PYTHONIOENCODING": "utf-8:replace",
}


@dataclass
class HookOutcome:
    """一次 hook 命令执行的结果。"""

    exit_code: int
    stdout: str
    stderr: str
    timed_out: bool = False


async def run_hook_command(
    command: str,
    payload: Dict,
    timeout: float = 30.0,
    cwd: Optional[str] = None,
) -> HookOutcome:
    """执行单条 hook 命令。

    任何失败（找不到命令、编码、超时）都转成非零 outcome，
    绝不向调用方抛异常——hook 是旁路设施，不能弄断主链路。
    """
    env = dict(os.environ)
    env.update(_CHILD_UTF8_ENV)
    # 对齐 Claude Code：hook 脚本可经 $CLAUDE_PROJECT_DIR 定位项目根
    if cwd:
        env["CLAUDE_PROJECT_DIR"] = str(cwd)

    try:
        proc = await asyncio.create_subprocess_shell(
            command,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=str(cwd) if cwd else None,
            env=env,
        )
    except Exception as e:
        logger.warning("hook spawn failed", command=command, error=str(e))
        return HookOutcome(exit_code=127, stdout="", stderr=f"spawn failed: {e}")

    stdin_data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    try:
        stdout_b, stderr_b = await asyncio.wait_for(
            proc.communicate(input=stdin_data), timeout=timeout
        )
    except asyncio.TimeoutError:
        # 超时强杀并收尸：非 daemon 子进程漏 wait 会变孤儿/挂退出；
        # 管道也显式关闭，避免 Windows 下 transport 被 GC 时抛 loop-closed 噪音
        try:
            proc.kill()
            await proc.wait()
            for pipe in (proc.stdin, proc.stdout, proc.stderr):
                if pipe is not None:
                    pipe.close()
        except Exception as e:
            logger.warning("hook kill failed", command=command, error=str(e))
        return HookOutcome(
            exit_code=124, stdout="", stderr=f"timeout after {timeout}s", timed_out=True
        )

    return HookOutcome(
        exit_code=proc.returncode if proc.returncode is not None else -1,
        stdout=stdout_b.decode("utf-8", errors="replace"),
        stderr=stderr_b.decode("utf-8", errors="replace"),
    )
