"""bash 会话 env 持久化测试（收敛批次④A）。

诚实边界：只捕获显式 export/set 赋值；脚本/子进程内的 export 对会话不可见。
平台自适应：Windows 走 cmd（set "K=V"），POSIX 走 sh（export K='V'）。
"""

import asyncio
import os

import pytest

from mini_claude.tools import bash as bash_mod
from mini_claude.tools.bash import (
    RunCommandTool,
    get_session_env,
    reset_session_env,
    set_session_env,
)


@pytest.fixture(autouse=True)
def _reset_env_and_cwd():
    reset_session_env()
    bash_mod.set_session_cwd(None)
    yield
    reset_session_env()
    bash_mod.set_session_cwd(None)


@pytest.mark.asyncio
async def test_export_persists_across_calls():
    """export 在一条命令里赋值，后续命令可见。"""
    tool = RunCommandTool()
    if os.name == "nt":
        r1 = await tool.execute('set "MC_TEST_VAR=hello"')
        r2 = await tool.execute("echo %MC_TEST_VAR%")
    else:
        r1 = await tool.execute("export MC_TEST_VAR=hello")
        r2 = await tool.execute("printenv MC_TEST_VAR")

    assert not r1.startswith("Error"), r1
    assert not r2.startswith("Error"), r2
    assert "hello" in r2, r2[:200]
    assert get_session_env().get("MC_TEST_VAR") == "hello"


@pytest.mark.asyncio
async def test_export_value_with_spaces():
    tool = RunCommandTool()
    if os.name == "nt":
        r1 = await tool.execute('set "MC_SPACED=two words here"')
        r2 = await tool.execute("echo %MC_SPACED%")
    else:
        r1 = await tool.execute("export MC_SPACED='two words here'")
        assert not r1.startswith("Error"), r1
        r2 = await tool.execute("printenv MC_SPACED")

    assert "two words here" in r2, r2[:200]


@pytest.mark.asyncio
async def test_posix_multi_assign_in_one_export():
    if os.name == "nt":
        pytest.skip("POSIX 语法用例")
    tool = RunCommandTool()
    await tool.execute("export MC_A=1 MC_B=2")
    env = get_session_env()
    assert env.get("MC_A") == "1" and env.get("MC_B") == "2"


@pytest.mark.asyncio
async def test_session_env_reaches_subprocess_env(tmp_path, monkeypatch):
    """收敛④A 最终设计：会话 env 经子进程 env= 参数注入（不走命令前缀——
    cmd 的 %VAR% 同行展开期会拿到旧值，实测踩中）。"""
    captured = {}

    class FakeProc:
        pid = 1

    async def fake_create_subprocess_shell(cmd, *a, **kw):
        captured["cmd"] = cmd
        captured["env"] = kw.get("env")
        return FakeProc()

    monkeypatch.setattr(asyncio, "create_subprocess_shell", fake_create_subprocess_shell)
    set_session_env({"MC_X": "1"})
    bash_mod.set_session_cwd(str(tmp_path))

    from mini_claude.tools.bash import RunBackgroundTool

    await RunBackgroundTool().execute("echo hi")
    assert "MC_X=1" not in captured["cmd"], "env 不应出现在命令行里"
    assert captured["env"]["MC_X"] == "1", "子进程环境必须携带会话 env"


def test_parse_env_assignments_posix_shapes():
    if os.name == "nt":
        pytest.skip("POSIX 解析用例")
    parse = bash_mod._parse_env_assignments
    assert parse("export A=1") == {"A": "1"}
    assert parse("export A='two words'") == {"A": "two words"}
    assert parse("export A=1 B=2") == {"A": "1", "B": "2"}
    assert parse("export BAD-NAME=1") == {}
    assert parse("ls") == {}
    assert parse("echo export A=1") == {}, "非 export 开头的行不解析"


def test_parse_env_assignments_cmd_shapes():
    if os.name != "nt":
        pytest.skip("cmd 解析用例")
    parse = bash_mod._parse_env_assignments
    assert parse('set "MC_V=hello world"') == {"MC_V": "hello world"}
    assert parse("set MC_V=plain") == {"MC_V": "plain"}
    assert parse("echo set MC_V=1") == {}
