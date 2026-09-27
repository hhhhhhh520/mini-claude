"""P4-2 task_output / task_kill 工具测试。

后台任务改为输出重定向到文件（顺带修掉 PIPE 缓冲写满会卡死子进程的隐患），
task_output 读文件，task_kill 杀进程。
"""

import sys
import asyncio

import pytest

from mini_claude.tools import list_tools
from mini_claude.tools.bash import (
    TaskKillTool,
    TaskOutputTool,
    _background_outputs,
    _background_processes,
    get_background_process_count,
)


def _py(tmp_path, code):
    """白名单禁 python -c（安全设计），测试改走脚本文件；-u 保证输出即时落盘"""
    p = tmp_path / f"t_{abs(hash(code))}.py"
    p.write_text(code, encoding="utf-8")
    return f'"{sys.executable}" -u "{p}"'


@pytest.fixture(autouse=True)
def _clean(monkeypatch):
    # 本文件测 task_output/task_kill 机制本身；命令白名单是另一套被测对象
    # （tests/test_utils/test_safety*），这里旁路以保持跨平台可跑。
    import mini_claude.tools.bash as bash_mod

    monkeypatch.setattr(bash_mod, "validate_command", lambda c: (True, "ok"))
    yield
    _background_processes.clear()
    _background_outputs.clear()


@pytest.mark.asyncio
async def test_tools_registered():
    assert "task_output" in list_tools()
    assert "task_kill" in list_tools()


@pytest.mark.asyncio
async def test_run_background_writes_output_file(tmp_path):
    from mini_claude.tools.bash import RunBackgroundTool

    result = await RunBackgroundTool().execute(command=_py(tmp_path, "print('bg-marker-42')"))
    assert result.startswith("Started background task")
    task_id = result.split("Started background task: ")[1].splitlines()[0].strip()
    assert task_id in _background_outputs, "run_background 必须登记输出文件"


@pytest.mark.asyncio
async def test_task_output_reads_content_and_finish_state(tmp_path):
    from mini_claude.tools.bash import RunBackgroundTool

    await RunBackgroundTool().execute(command=_py(tmp_path, "print('bg-marker-42')"))
    assert _background_outputs, "run_background 应登记输出文件"
    task_id = next(iter(_background_outputs))

    out_tool = TaskOutputTool()
    # 轮询等子进程真正退出（CI 慢机器友好）
    content = ""
    for _ in range(50):
        content = await out_tool.execute(task_id=task_id)
        if "finished" in content.lower() and "bg-marker-42" in content:
            break
        # 必须用 asyncio.sleep：同步 sleep 会阻塞事件循环，
        # 子进程退出回调得不到调度，returncode 永远不更新（实踩）
        await asyncio.sleep(0.2)
    assert "bg-marker-42" in content
    assert "finished" in content.lower() and "exit code" in content.lower()


@pytest.mark.asyncio
async def test_task_output_running_state(tmp_path):
    from mini_claude.tools.bash import RunBackgroundTool

    await RunBackgroundTool().execute(
        command=_py(tmp_path, "print('partial-line'); import time; time.sleep(30)")
    )
    task_id = next(iter(_background_outputs))
    # 子进程 spawn + 首行输出需要时间：短轮询验证"运行中输出可见"
    content = ""
    for _ in range(30):
        content = await TaskOutputTool().execute(task_id=task_id)
        if "partial-line" in content:
            break
        await asyncio.sleep(0.2)
    assert "partial-line" in content  # 未结束也能读到已产出的输出
    assert "running" in content.lower()


@pytest.mark.asyncio
async def test_task_kill_terminates(tmp_path):
    from mini_claude.tools.bash import RunBackgroundTool

    await RunBackgroundTool().execute(command=_py(tmp_path, "import time; time.sleep(120)"))
    task_id = next(iter(_background_processes))

    result = await TaskKillTool().execute(task_id=task_id)
    assert "Error" not in result
    proc = _background_processes.get(task_id)
    if proc is not None:  # kill 后可能已被清理出表，留容忍
        assert proc.returncode is not None, "kill 后进程应已终止"


@pytest.mark.asyncio
async def test_task_output_unknown_id_lists_available(tmp_path):
    from mini_claude.tools.bash import RunBackgroundTool

    await RunBackgroundTool().execute(command=_py(tmp_path, "print('x')"))
    assert _background_outputs
    known = next(iter(_background_outputs))
    result = await TaskOutputTool().execute(task_id="task_nope")
    assert result.startswith("Error")
    assert known in result, "未知 task_id 的报错应列出可用 id"

    await TaskKillTool().execute(task_id=known)


@pytest.mark.asyncio
async def test_task_kill_unknown_id():
    result = await TaskKillTool().execute(task_id="task_nope")
    assert result.startswith("Error")


@pytest.mark.asyncio
async def test_background_count_still_works(tmp_path):
    from mini_claude.tools.bash import RunBackgroundTool

    before = get_background_process_count()
    await RunBackgroundTool().execute(command=_py(tmp_path, "import time; time.sleep(60)"))
    assert get_background_process_count() == before + 1


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
