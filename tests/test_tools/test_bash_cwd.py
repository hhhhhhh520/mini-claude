"""bash 会话 cwd 持久化测试（收敛批次③D）。

诚实边界：持久的是工作目录，env 不持久。平台自适应：Windows 走 cmd
语法（cd /d、%CD%），POSIX 走 sh 语法（&&、$PWD）——测试按 os.name 分支。
"""

import asyncio
import os

import pytest

from mini_claude.tools import bash as bash_mod
from mini_claude.tools.bash import RunCommandTool, get_session_cwd, set_session_cwd


@pytest.fixture(autouse=True)
def _reset_cwd():
    set_session_cwd(None)
    yield
    set_session_cwd(None)


@pytest.mark.asyncio
async def test_cwd_persists_across_calls(tmp_path):
    """第一条命令 cd 进子目录，第二条命令应在同一目录里执行。"""
    tool = RunCommandTool()
    target = tmp_path / "sub"
    target.mkdir()

    if os.name == "nt":
        r1 = await tool.execute(f'cd /d "{target}"')
        r2 = await tool.execute("cd")
    else:
        r1 = await tool.execute(f'cd "{target}"')
        r2 = await tool.execute("pwd")

    assert not r1.startswith("Error"), r1
    assert not r2.startswith("Error"), r2
    assert str(target) in r2 or target.name in r2, f"第二条命令应看到子目录：{r2[:200]}"
    assert get_session_cwd() is not None


@pytest.mark.asyncio
async def test_sentinel_stripped_from_output():
    """哨兵行不出现在给 LLM 的输出里。"""
    tool = RunCommandTool()
    r = await tool.execute("echo hello")
    assert "hello" in r
    assert "__MC_CWD__" not in r


@pytest.mark.asyncio
async def test_session_cwd_prefix_applied(tmp_path):
    """预置会话 cwd：命令不改目录也在该目录执行。"""
    set_session_cwd(str(tmp_path))
    tool = RunCommandTool()
    if os.name == "nt":
        r = await tool.execute("cd")
    else:
        r = await tool.execute("pwd")
    assert str(tmp_path) in r, r[:200]


@pytest.mark.asyncio
async def test_failing_command_still_updates_cwd(tmp_path):
    """命令失败（exit≠0）时哨兵捕获仍应生效（cd 到不存在的目录）。"""
    tool = RunCommandTool()
    missing = tmp_path / "missing_dir"
    if os.name == "nt":
        r = await tool.execute(f'cd /d "{missing}"')
    else:
        r = await tool.execute(f'cd "{missing}"')
    assert not r.startswith("Error")
    assert "Exit code: 1" in r or "Exit code: 0" in r
    assert "__MC_CWD__" not in r
    assert get_session_cwd() is not None, "失败的命令也带回最终 cwd（=原目录）"
    assert get_session_cwd() is not None, "失败的命令也要带回最终 cwd"


@pytest.mark.asyncio
async def test_background_prefix_without_capture(tmp_path, monkeypatch):
    """后台命令加 cd 前缀、不加哨兵捕获（进程长驻无"结束后"）。"""
    captured = {}

    class FakeProc:
        pid = 1

    async def fake_create_subprocess_shell(cmd, *a, **kw):
        captured["cmd"] = cmd
        return FakeProc()

    monkeypatch.setattr(asyncio, "create_subprocess_shell", fake_create_subprocess_shell)

    set_session_cwd(str(tmp_path))
    from mini_claude.tools.bash import RunBackgroundTool

    await RunBackgroundTool().execute("echo hi")
    assert "echo hi" in captured["cmd"]
    if os.name == "nt":
        assert "cd /d" in captured["cmd"]
    else:
        assert 'cd "' in captured["cmd"]
    assert bash_mod._CWD_SENTINEL not in captured["cmd"], "后台命令不加哨兵"
