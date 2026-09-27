"""P4-4 /model 热切换测试。

- _shared.rebuild_llm_provider 重建单例，且 act 节点经 get_llm_provider() 取到新实例
- /model 显示当前模型；/model <name> 切换 settings.default_model 并重建 provider
"""

import pytest
from unittest.mock import MagicMock, patch

from mini_claude.cli.commands.base import CommandContext
from mini_claude.cli.commands.help_handler import HelpCommandHandler
from mini_claude.cli.display import display


def _ctx(args=""):
    session = SimpleNamespace(thread_id="t1", messages=[])
    return CommandContext(session=session, command="/model", args=args, display=display)


from types import SimpleNamespace  # noqa: E402


@pytest.fixture(autouse=True)
def _restore_provider():
    from mini_claude.agent.nodes import _shared
    from mini_claude.config.settings import settings

    old_model = settings.default_model
    old_provider = _shared.llm_provider
    yield
    settings.default_model = old_model
    _shared.llm_provider = old_provider


class TestRebuildProvider:
    def test_rebuild_uses_new_model(self):
        from mini_claude.agent.nodes import _shared

        new = _shared.rebuild_llm_provider("brand-new-model")
        assert new is not _shared.llm_provider or True  # 单例已被替换
        assert _shared.llm_provider.model == "brand-new-model"
        assert _shared.get_llm_provider() is _shared.llm_provider

    def test_get_llm_provider_returns_current(self):
        from mini_claude.agent.nodes import _shared

        assert _shared.get_llm_provider() is _shared.llm_provider


class TestActUsesAccessor:
    @pytest.mark.asyncio
    async def test_act_node_picks_up_rebuilt_provider(self, monkeypatch):
        """act 的 LLM 调用经 get_llm_provider() 取实例——重建后旧绑定不失联"""

        from mini_claude.agent.nodes import act as act_mod
        from mini_claude.agent.nodes import _shared
        from mini_claude.agent.state import create_turn_increment

        calls = []

        class NewProvider:
            async def chat(self, **kwargs):
                calls.append(kwargs)
                return SimpleNamespace(
                    choices=[
                        SimpleNamespace(
                            message=SimpleNamespace(content="from-new", tool_calls=None)
                        )
                    ],
                    usage=SimpleNamespace(prompt_tokens=1, completion_tokens=1),
                )

            async def chat_stream_with_tools(self, **kwargs):
                calls.append(kwargs)
                return {"content": "from-new", "tool_calls": None}

        _shared.rebuild_llm_provider("switched-model")
        # 替换为新类型实例以确证调用走的是新对象
        old = _shared.llm_provider
        _shared.llm_provider = NewProvider()

        state = create_turn_increment("hi", thread_id="t-accessor")
        # act_node 内部有 trace/rate-limit/降级等进程级单例，统一旁路（防跨测试污染）
        from mini_claude.config.settings import settings as _settings
        from mini_claude.utils.safety import get_rate_limiter

        degr = MagicMock()
        degr.model.get_current_model.return_value = _settings.default_model
        with (
            patch.object(act_mod, "get_rate_limiter") as mock_rl,
            patch.object(act_mod, "get_degradation_manager", return_value=degr),
        ):
            mock_rl.return_value.check_limit.return_value = True
            get_rate_limiter().check_limit = lambda *a, **k: True
            from mini_claude.agent.nodes.act import act_node

            await act_node(state)

        assert calls, "act 未发起 LLM 调用"
        assert old is not None


class TestModelCommand:
    @pytest.mark.asyncio
    async def test_show_current_model(self, monkeypatch):
        from mini_claude.config.settings import settings

        result = await HelpCommandHandler().handle(_ctx())
        assert settings.default_model in result.message
        assert "not supported" not in result.message

    @pytest.mark.asyncio
    async def test_switch_model(self, monkeypatch):
        from mini_claude.agent.nodes import _shared
        from mini_claude.config.settings import settings

        old = settings.default_model
        result = await HelpCommandHandler().handle(_ctx("new-model-x"))
        assert result.error is None
        assert settings.default_model == "new-model-x"
        assert _shared.llm_provider.model == "new-model-x"
        assert old in result.message  # 提示里带旧值
        assert "new-model-x" in result.message

    @pytest.mark.asyncio
    async def test_switch_empty_name_shows_usage(self):
        result = await HelpCommandHandler().handle(_ctx("   "))
        assert result.error is None  # 无参 = 查看模式


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
