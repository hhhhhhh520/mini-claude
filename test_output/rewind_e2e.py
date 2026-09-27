"""P4 真 Key E2E：真实 LLM 多轮会话 + /rewind 分叉 + 连接无泄漏。

等价于 REPL 的真实回合流程（唯一 mock 是没有 REPL 终端本身）：
- 真实 LLM（.env 网关）跑两轮
- get_state_history 找第一轮结束的边界 → fork 增量重跑
- 断言：无消息复制、分叉结果正确、close_checkpoint_connections 后进程干净退出
"""

import asyncio
import os
import sys
import tempfile

sys.path.insert(0, os.path.abspath("."))


async def main():
    from langchain_core.messages import HumanMessage

    from mini_claude.agent.graph import (
        build_agent_graph,
        close_checkpoint_connections,
    )
    from mini_claude.agent.state import create_turn_increment
    from mini_claude.cli.main import _suppress_third_party_stdout_noise

    _suppress_third_party_stdout_noise()

    db = os.path.join(tempfile.mkdtemp(), "rewind_e2e.db")
    graph = build_agent_graph(checkpointer_path=db)
    tid = "t-rewind-e2e"
    cfg = {"configurable": {"thread_id": tid}, "recursion_limit": 50}

    await graph.ainvoke(create_turn_increment("用一句话回答：1+1 等于几？", thread_id=tid), cfg)
    r2 = await graph.ainvoke(
        create_turn_increment("再用一句话回答：2+2 等于几？", thread_id=tid), cfg
    )

    humans2 = [str(m.content) for m in r2["messages"] if isinstance(m, HumanMessage)]
    assert humans2 == ["用一句话回答：1+1 等于几？", "再用一句话回答：2+2 等于几？"], (
        f"多轮不得复制历史：{humans2}"
    )
    print("[1] 多轮无复制 OK:", humans2)

    # 找第一轮结束的边界（含 1+1 不含 2+2）
    boundaries = [
        s
        async for s in graph.aget_state_history({"configurable": {"thread_id": tid}})
        if s.next in (("think",), ())
    ]
    pick = next(
        s
        for s in boundaries
        if any("1+1" in str(getattr(m, "content", "")) for m in s.values["messages"])
        and not any("2+2" in str(getattr(m, "content", "")) for m in s.values["messages"])
    )
    fork_cfg = {
        "configurable": {
            "thread_id": tid,
            "checkpoint_id": pick.config["configurable"]["checkpoint_id"],
        },
        "recursion_limit": 50,
    }
    r3 = await graph.ainvoke(
        create_turn_increment("分叉验证：用一句话回答 3+3 等于几？", thread_id=tid),
        fork_cfg,
    )
    humans3 = [str(m.content) for m in r3["messages"] if isinstance(m, HumanMessage)]
    assert "2+2" not in "".join(humans3), f"分叉后旧第二轮不应存在：{humans3}"
    assert any("分叉验证" in c for c in humans3)
    print("[2] rewind 分叉 OK:", humans3)

    closed = await close_checkpoint_connections()
    assert closed >= 1, "checkpoint 连接未关闭（进程会挂）"
    print("[3] 连接收口 OK: closed =", closed)
    print("P4 REAL-KEY E2E: ALL PASS")


asyncio.run(main())
