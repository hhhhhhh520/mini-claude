"""MCP 断连收口健壮性测试（实际测试发现的缺陷回归锁）。

真实 REPL 退出链路：run_graph finally → close_mcp_connections → disconnect_server
→ stack.aclose()。实测踩中两类爆点：
① anyio cancel scope 内部取消风暴抛 CancelledError（BaseException），穿透
   ``except Exception`` 冲出 REPL 退出链路；
② 拆到独立任务/wait_for 里 aclose 会炸 "Attempted to exit cancel scope in a
   different task"——aclose 必须留在进入连接的同一任务里直接 await。
所以本文件锁定：同任务 await + 吞一切异常（含 CancelledError 族）。
"""

from types import SimpleNamespace

import pytest

from mini_claude.mcp.manager import McpManager, reset_mcp_manager


@pytest.fixture(autouse=True)
def _cleanup():
    reset_mcp_manager()
    yield
    reset_mcp_manager()


def _manager_with_conn(aclose):
    mgr = McpManager()
    mgr._connections = {
        "srv": SimpleNamespace(
            server="srv", session=None, tools=[], stack=SimpleNamespace(aclose=aclose)
        )
    }
    return mgr


@pytest.mark.asyncio
async def test_aclose_exception_swallowed():
    """aclose 抛普通异常：不外抛，连接已出表。"""

    async def boom():
        raise RuntimeError("子进程僵死")

    mgr = _manager_with_conn(boom)
    await mgr.disconnect_server("srv")
    assert "srv" not in mgr._connections


@pytest.mark.asyncio
async def test_aclose_cancelled_error_swallowed():
    """取消风暴（CancelledError 是 BaseException）：同样吞掉，不冲出退出链路。"""

    async def cancelled():
        raise asyncio.CancelledError()

    import asyncio

    mgr = _manager_with_conn(cancelled)
    await mgr.disconnect_server("srv")
    assert "srv" not in mgr._connections


@pytest.mark.asyncio
async def test_aclose_runs_in_caller_task(monkeypatch):
    """aclose 必须在调用方任务里执行（anyio cancel scope 同任务约束）。"""
    import asyncio

    seen_task = {}

    async def record():
        seen_task["task"] = asyncio.current_task()
        return None

    mgr = _manager_with_conn(record)
    await mgr.disconnect_server("srv")
    assert seen_task["task"] is asyncio.current_task(), "aclose 不得拆到别的任务"


@pytest.mark.asyncio
async def test_disconnect_unknown_server_noop():
    mgr = McpManager()
    await mgr.disconnect_server("never-connected")  # 幂等，不抛


@pytest.mark.asyncio
async def test_close_all_survives_one_bad_connection():
    """close_all：一个 server 关不掉不影响其他 server 收口。"""

    async def boom():
        raise RuntimeError("挂了")

    async def ok():
        return None

    mgr = McpManager()
    mgr._connections = {
        "bad": SimpleNamespace(
            server="bad", session=None, tools=[], stack=SimpleNamespace(aclose=boom)
        ),
        "good": SimpleNamespace(
            server="good", session=None, tools=[], stack=SimpleNamespace(aclose=ok)
        ),
    }
    await mgr.close_all()
    assert mgr._connections == {}
