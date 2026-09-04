"""主图 checkpointer 装配的端到端契约测试.

为什么存在这个文件
------------------
2026-09-04 发现：REPL 是主图的唯一**生产**调用方（另一条
`context/providers.py:create_agent_graph` 当前无调用者），但**修复前全仓库没有任何
测试调用过 `build_agent_graph()` / `get_agent_graph()`**——
`tests/test_integration/test_agent_flow.py` 与 `test_e2e_user_flow.py` 全部用
`build_agent_graph_no_checkpoint()`。因此修复前 `graph.py:109`（现 `:120-131`）把
`AsyncSqliteSaver.from_conn_string()` 的返回值——一个 `@asynccontextmanager`
产出的 context manager，而非 saver——直接传给 `graph.compile(checkpointer=...)`。
该缺陷存活了 2 个月零 9 天（引入于 commit 9d59f60），期间 PROGRESS.md 一直
声称「1673 测试通过」「核心功能完成」。

本文件测的是**外部契约**，不是实现细节：
  1. 编译出的图，其 checkpointer 必须是一个真正的 BaseCheckpointSaver；
  2. 一次真实 `ainvoke` 必须能跑完而不抛；
  3. 跑完后 SQLite 里必须真的落 checkpoint（这是 CLAUDE.md:38-43 承诺的
     「进程退出后状态持久化、/resume 可用」的唯一证据）。

compile 相关的断言刻意不读 `graph.py` 里的那行代码——否则就变成同义反复测试了。
例外：三条 close 用例断言了 `_checkpoint_conns` / `_agent_graph` 私有模块态，
那是因为它们要验的就是登记与复位本身。
"""

import sqlite3
from types import SimpleNamespace

import pytest

from langgraph.checkpoint.base import BaseCheckpointSaver

from mini_claude.agent.graph import build_agent_graph
from mini_claude.agent.state import create_initial_state


@pytest.fixture(autouse=True)
async def _drain_checkpoint_conns():
    """每个用例后关闭连接，避免用例间互相泄漏 / Windows 上临时库文件被占用."""
    from mini_claude.agent.graph import close_checkpoint_connections

    yield
    await close_checkpoint_connections()


@pytest.fixture
def fake_provider(monkeypatch):
    """把 LLM 换成可控替身，让测试不依赖网络与 API 余额.

    patch 的是 `_shared.llm_provider` 这个**单例对象上的方法**，
    因此 `act.py:22`（import 期按名绑定）与 `check_completion.py:73` /
    `reflect.py:152`（调用期函数内 import）两条路径都覆盖到。
    """
    from mini_claude.agent.nodes import _shared

    provider = _shared.llm_provider

    msg = SimpleNamespace(content="已完成，无需再调用工具。", tool_calls=None)
    response = SimpleNamespace(
        choices=[SimpleNamespace(message=msg)],
        usage=SimpleNamespace(prompt_tokens=10, completion_tokens=5),
    )

    async def fake_chat(*args, **kwargs):
        return response

    async def fake_chat_stream_with_tools(*args, **kwargs):
        return {"content": msg.content, "tool_calls": None}

    monkeypatch.setattr(provider, "chat", fake_chat)
    monkeypatch.setattr(provider, "chat_stream_with_tools", fake_chat_stream_with_tools)
    return provider


def _checkpoint_row_count(db_path: str, thread_id: str) -> int:
    conn = sqlite3.connect(db_path)
    try:
        tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        if "checkpoints" not in tables:
            return -1
        return conn.execute(
            "SELECT COUNT(*) FROM checkpoints WHERE thread_id = ?", (thread_id,)
        ).fetchone()[0]
    finally:
        conn.close()


@pytest.mark.parametrize("streaming", [True, False], ids=["stream", "non-stream"])
async def test_main_graph_has_real_checkpointer(tmp_path, fake_provider, streaming, monkeypatch):
    """checkpointer 必须是真 saver，不是 asynccontextmanager 的产物."""
    from mini_claude.config.settings import settings

    monkeypatch.setattr(settings, "streaming_enabled", streaming)
    db = str(tmp_path.resolve() / "ckpt.db")

    graph = build_agent_graph(checkpointer_path=db)

    checkpointer = getattr(graph, "checkpointer", None)
    assert checkpointer is not None, "图未装配 checkpointer，/resume 与断点续跑不可能生效"
    assert isinstance(checkpointer, BaseCheckpointSaver), (
        f"checkpointer 类型错误：拿到 {type(checkpointer).__name__}，"
        "它应是 BaseCheckpointSaver 实例。"
        "AsyncSqliteSaver.from_conn_string() 是 @asynccontextmanager，"
        "直接传给 compile() 会得到 context manager 而非 saver。"
    )


@pytest.mark.parametrize("streaming", [True, False], ids=["stream", "non-stream"])
async def test_main_graph_ainvoke_completes(tmp_path, fake_provider, streaming, monkeypatch):
    """一轮真实图执行必须跑完，而不是每轮抛异常."""
    from mini_claude.config.settings import settings

    monkeypatch.setattr(settings, "streaming_enabled", streaming)
    db = str(tmp_path.resolve() / "ckpt.db")
    thread_id = "thread-e2e-1"

    graph = build_agent_graph(checkpointer_path=db)
    state = create_initial_state("说一句话就好", thread_id=thread_id)

    result = await graph.ainvoke(
        state,
        {"configurable": {"thread_id": thread_id}, "recursion_limit": 50},
    )

    assert "messages" in result and len(result["messages"]) >= 2, (
        f"图执行未产出对话，实际 keys={list(result)}"
    )


@pytest.mark.parametrize("streaming", [True, False], ids=["stream", "non-stream"])
async def test_main_graph_persists_checkpoint_to_sqlite(
    tmp_path, fake_provider, streaming, monkeypatch
):
    """跑完必须在 SQLite 里留下该 thread 的 checkpoint（持久化的唯一证据）."""
    from mini_claude.config.settings import settings

    monkeypatch.setattr(settings, "streaming_enabled", streaming)
    db = str(tmp_path.resolve() / "ckpt.db")
    thread_id = "thread-e2e-persist"

    graph = build_agent_graph(checkpointer_path=db)
    await graph.ainvoke(
        create_initial_state("说一句话就好", thread_id=thread_id),
        {"configurable": {"thread_id": thread_id}, "recursion_limit": 50},
    )

    rows = _checkpoint_row_count(db, thread_id)
    assert rows > 0, (
        f"checkpoint 未落库：db={db} 中 thread_id={thread_id!r} 的行数={rows}"
        "（-1 表示连 checkpoints 表都不存在）。"
        "这意味着进程退出后状态丢失、/resume 与启动恢复提示全部失效。"
    )


async def test_checkpoint_survives_graph_rebuild(tmp_path, fake_provider, monkeypatch):
    """跨「进程级重建图」读回状态——模拟重启后靠 SQLite 恢复.

    归因说明：真正区分 MemorySaver 与真持久化的守门断言是
    `test_main_graph_persists_checkpoint_to_sqlite`（它直接读 .db 文件，
    表不存在就 -1）。本条额外守住的是「每次 build 都新建 saver」这一情形下
    跨重建只靠落盘恢复；若有人把 MemorySaver 提升为模块级单例，本条会转绿而
    落库读文件那条仍然红。
    """
    from mini_claude.config.settings import settings

    monkeypatch.setattr(settings, "streaming_enabled", False)
    db = str(tmp_path.resolve() / "ckpt.db")
    thread_id = "thread-resume-sim"

    first = build_agent_graph(checkpointer_path=db)
    await first.ainvoke(
        create_initial_state("第一条消息", thread_id=thread_id),
        {"configurable": {"thread_id": thread_id}, "recursion_limit": 50},
    )

    # 模拟重启：重新构建图（全新 checkpointer 对象），只靠 SQLite 恢复
    second = build_agent_graph(checkpointer_path=db)
    snapshot = await second.aget_state({"configurable": {"thread_id": thread_id}})

    assert snapshot is not None and snapshot.values, (
        "重建图后读不到该 thread 的状态 —— SQLite 持久化没有生效"
    )
    contents = [str(getattr(m, "content", "")) for m in snapshot.values.get("messages", [])]
    assert any("第一条消息" in c for c in contents), (
        f"恢复出的历史里找不到原始输入，实际消息={contents}"
    )


async def test_close_checkpoint_connections_actually_closes(tmp_path, fake_provider, monkeypatch):
    """close 必须真的关掉连接，而不是只把列表清空.

    判据：关闭后再用同一张图写 checkpoint 必须失败。若实现只是
    `_checkpoint_conns = []`，本测试会红。
    """
    import sqlite3 as _sqlite3

    from mini_claude.agent import graph as graph_mod
    from mini_claude.config.settings import settings

    monkeypatch.setattr(settings, "streaming_enabled", False)
    db = str(tmp_path.resolve() / "ckpt.db")
    thread_id = "thread-close-1"

    built = graph_mod.build_agent_graph(checkpointer_path=db)
    await built.ainvoke(
        create_initial_state("说一句话就好", thread_id=thread_id),
        {"configurable": {"thread_id": thread_id}, "recursion_limit": 50},
    )

    assert graph_mod._checkpoint_conns, "build_agent_graph 未登记连接，close 无从下手"

    # 先让单例真的被建立，否则「close 后 _agent_graph is None」是恒真断言
    # （模块导入时它本来就是 None，对复位逻辑零判别力）。
    singleton = graph_mod.get_agent_graph()
    assert singleton is not None
    assert graph_mod._agent_graph is not None, "前置条件不成立：图单例未被建立"

    registered = len(graph_mod._checkpoint_conns)
    closed = await graph_mod.close_checkpoint_connections()
    assert closed == registered, f"登记 {registered} 条却只关闭 {closed} 条"
    assert graph_mod._checkpoint_conns == [], "close 后仍残留登记"
    assert graph_mod._agent_graph is None, "close 未复位图单例，重启会话会复用已关连接的图"

    with pytest.raises(Exception):
        await built.ainvoke(
            create_initial_state("关闭后还应能写", thread_id="thread-close-2"),
            {"configurable": {"thread_id": "thread-close-2"}, "recursion_limit": 50},
        )

    # 已落库的数据不因关闭而损坏
    assert _checkpoint_row_count(db, thread_id) > 0, "关闭后既有 checkpoint 读不到了"
    _sqlite3.connect(db).close()


async def test_close_is_idempotent(tmp_path, fake_provider, monkeypatch):
    """先真关一批连接、再关第二次——覆盖「退出路径被走两次」.

    注意不能让 autouse fixture 先把登记表清空，否则两次 close 都发生在空表上，
    本用例就退化成恒真断言。所以这里显式建图，并断言第一次关掉了东西。
    """
    from mini_claude.agent import graph as graph_mod
    from mini_claude.config.settings import settings

    monkeypatch.setattr(settings, "streaming_enabled", False)
    db = str(tmp_path.resolve() / "idem.db")
    built = graph_mod.build_agent_graph(checkpointer_path=db)
    await built.ainvoke(
        create_initial_state("说一句话就好", thread_id="thread-idem"),
        {"configurable": {"thread_id": "thread-idem"}, "recursion_limit": 50},
    )

    first = await graph_mod.close_checkpoint_connections()
    assert first >= 1, f"第一次 close 什么都没关（{first}），第二次==0 的断言将无意义"
    assert await graph_mod.close_checkpoint_connections() == 0


async def test_repl_exit_path_closes_connections(tmp_path, fake_provider, monkeypatch):
    """生产 cleanup 调用点必须真的被走到.

    只有 `close_checkpoint_connections()` 函数而无调用点保护 = 资源照漏。
    本用例驱动 REPLSession.run_graph 走 EOFError（Ctrl+D）退出路径，断言
    run_graph 的 finally 确实调用了它——把 `repl.py` 里的 finally 删掉本测试即红。
    """
    from mini_claude.agent import graph as graph_mod
    from mini_claude.cli.repl import REPLSession
    from mini_claude.config.settings import settings

    monkeypatch.setattr(settings, "streaming_enabled", False)
    monkeypatch.setattr(settings, "session_db_path", str(tmp_path.resolve() / "repl.db"))

    calls = []
    real_close = graph_mod.close_checkpoint_connections

    async def spy():
        calls.append(len(graph_mod._checkpoint_conns))
        return await real_close()

    monkeypatch.setattr(graph_mod, "close_checkpoint_connections", spy)

    class _PromptRaisesEOF:
        async def prompt_async(self, *args, **kwargs):
            raise EOFError

    session = REPLSession()
    session.session = _PromptRaisesEOF()

    await session.run_graph()

    assert calls, "run_graph 退出时未关闭 checkpoint 连接（后台 bash 进程同理，别只测一个）"
    assert calls[0] >= 1, f"走到 close 时登记表已空（{calls[0]}），说明图没建或提前被关"
