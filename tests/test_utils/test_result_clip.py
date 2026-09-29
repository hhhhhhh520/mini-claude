"""工具结果尺寸上限测试（收敛批次②C）。"""

import pytest
from types import SimpleNamespace

from mini_claude.utils.result_clip import clip_tool_result


@pytest.fixture
def small_limit(monkeypatch):
    from mini_claude.config.settings import settings

    monkeypatch.setattr(settings, "tool_result_max_chars", 100)


class TestClipToolResult:
    def test_short_result_unchanged(self):
        assert clip_tool_result("hello", max_chars=100) == "hello"

    def test_over_limit_truncated_with_note(self, small_limit):
        text = "x" * 500
        out = clip_tool_result(text)
        assert len(out) < 200
        assert out.startswith("x" * 10)
        assert "已截断" in out and "500" in out, "必须告知原始长度"

    def test_exact_limit_unchanged(self, small_limit):
        text = "y" * 100
        assert clip_tool_result(text) == text

    def test_explicit_max_chars_overrides_settings(self, small_limit):
        text = "z" * 50
        out = clip_tool_result(text, max_chars=10)
        assert "50" in out and len(out) < 60

    def test_none_becomes_empty(self):
        assert clip_tool_result(None) == ""

    @pytest.mark.asyncio
    async def test_act_chain_clips_tool_message(self, monkeypatch):
        """act 执行链的 ToolMessage 必须吃到上限（超长结果不进 context）。"""
        from mini_claude.agent.nodes._act_helpers import execute_single_tool

        async def fake_execute_tool(name, params):
            return "R" * 500

        import mini_claude.tools as tools_pkg

        monkeypatch.setattr(tools_pkg, "execute_tool", fake_execute_tool)

        degr = SimpleNamespace(
            tool=SimpleNamespace(
                should_skip=lambda n: False,
                get_replacement=lambda n: None,
                record_success=lambda n: None,
                record_failure=lambda *a, **k: None,
            )
        )
        metrics = SimpleNamespace(record_tool_call=lambda *a, **k: None)
        import contextlib

        trace = lambda *a, **k: contextlib.nullcontext()  # noqa: E731

        from mini_claude.config.settings import settings

        monkeypatch.setattr(settings, "tool_result_max_chars", 100)

        messages = []
        await execute_single_tool(
            "gate_probe",
            {},
            degr,
            metrics,
            trace,
            messages,
            tool_call_id="call_1",
        )
        assert len(messages) == 1
        content = messages[0].content
        assert len(content) < 300, "ToolMessage 内容必须被截断"
        assert "已截断" in content and messages[0].status == "success"
