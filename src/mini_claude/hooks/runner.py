"""hook 命令执行器（P3-1）。

用户自配的受信命令，经 shell 执行：JSON payload 走 stdin，
exit code / stdout / stderr 回传。超时强杀（复用"非 daemon 子进程必须收尸"纪律）。
"""

import asyncio
import json
from dataclasses import dataclass
from typing import Dict, Optional

from ..utils.logger import get_logger

logger = get_logger("mini_claude.hooks.runner")


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
    try:
        proc = await asyncio.create_subprocess_shell(
            command,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=str(cwd) if cwd else None,
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
        # 超时强杀并收尸：非 daemon 子进程漏 wait 会变孤儿/挂退出
        try:
            proc.kill()
            await proc.wait()
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
