"""checkpoint serde 白名单测试（ISSUE-027）。

StopReason 是自定义枚举，进 checkpoint 走 LangGraph msgpack ext 编码。
未注册白名单时每次反序列化都告警，且 LangGraph 未来版本默认阻断
（/resume、/rewind、全部带 checkpointer 的测试将失效）。
graph.build_agent_graph 必须显式允许 ('mini_claude.agent.state', 'StopReason')。
"""

import pytest

from mini_claude.agent.state import StopReason


@pytest.mark.asyncio
async def test_stop_reason_in_msgpack_allowlist(tmp_path):
    from mini_claude.agent.graph import build_agent_graph

    graph = build_agent_graph(checkpointer_path=str(tmp_path / "serde_test.db"))
    serde = graph.checkpointer.serde

    allowed = serde._allowed_msgpack_modules
    assert allowed is True or ("mini_claude.agent.state", "StopReason") in allowed, (
        f"StopReason 必须在 msgpack 白名单里，实际：{allowed}"
    )


@pytest.mark.asyncio
async def test_stop_reason_roundtrip_through_serde(tmp_path):
    """checkpoint 里的 StopReason 必须能无损往返（含未来严格模式）"""
    from mini_claude.agent.graph import build_agent_graph

    graph = build_agent_graph(checkpointer_path=str(tmp_path / "serde_test.db"))
    serde = graph.checkpointer.serde

    for reason in StopReason:
        blob = serde.dumps_typed(reason)
        assert serde.loads_typed(blob) == reason, f"{reason} 经 checkpoint serde 往返失真"
