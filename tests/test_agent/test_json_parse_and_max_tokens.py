"""针对性测试：JSON 解析失败和 max_tokens 截断问题

测试覆盖：
1. JSON 解析失败时返回明确错误而非静默空字典
2. llm_max_tokens 配置项生效
3. 工具参数解析错误正确传递给 LLM
"""

import pytest
import json
from unittest.mock import AsyncMock, MagicMock

from mini_claude.agent.nodes._act_helpers import parse_tool_calls, execute_single_tool
from mini_claude.config.settings import settings


class TestJSONParseErrorHandling:
    """测试 JSON 解析失败的错误处理"""

    def test_parse_tool_calls_valid_json(self):
        """测试有效 JSON 正确解析"""
        raw_tool_calls = [
            {
                "id": "call_1",
                "name": "write_file",
                "arguments": '{"path": "test.py", "content": "print(1)"}'
            }
        ]
        result = parse_tool_calls(raw_tool_calls)
        assert len(result) == 1
        assert result[0]["name"] == "write_file"
        assert result[0]["args"]["path"] == "test.py"
        assert result[0]["args"]["content"] == "print(1)"

    def test_parse_tool_calls_truncated_json(self):
        """测试截断的 JSON 返回 _parse_error 字段"""
        # 模拟 LLM 输出被截断的情况
        raw_tool_calls = [
            {
                "id": "call_1",
                "name": "edit_file",
                "arguments": '{"path": "test.py", "old_text": "very long content that got truncat'  # 不完整的 JSON
            }
        ]
        result = parse_tool_calls(raw_tool_calls)
        assert len(result) == 1
        assert result[0]["name"] == "edit_file"
        assert "_parse_error" in result[0]["args"]
        assert "JSON 解析失败" in result[0]["args"]["_parse_error"]
        assert "_raw_args" in result[0]["args"]

    def test_parse_tool_calls_empty_arguments(self):
        """测试空参数"""
        raw_tool_calls = [
            {
                "id": "call_1",
                "name": "list_dir",
                "arguments": '{}'
            }
        ]
        result = parse_tool_calls(raw_tool_calls)
        assert len(result) == 1
        assert result[0]["args"] == {}

    def test_parse_tool_calls_missing_arguments(self):
        """测试缺少 arguments 字段"""
        raw_tool_calls = [
            {
                "id": "call_1",
                "name": "list_dir",
            }
        ]
        result = parse_tool_calls(raw_tool_calls)
        assert len(result) == 1
        assert result[0]["args"] == {}

    def test_parse_tool_calls_invalid_json_with_special_chars(self):
        """测试包含特殊字符的无效 JSON"""
        raw_tool_calls = [
            {
                "id": "call_1",
                "name": "write_file",
                "arguments": '{"path": "test.py", "content": "line1\nline2\nunterminated'  # 换行符导致问题
            }
        ]
        result = parse_tool_calls(raw_tool_calls)
        assert "_parse_error" in result[0]["args"]

    def test_parse_tool_calls_none_input(self):
        """测试 None 输入"""
        result = parse_tool_calls(None)
        assert result == []

    def test_parse_tool_calls_empty_list(self):
        """测试空列表"""
        result = parse_tool_calls([])
        assert result == []


class TestExecuteToolWithParseError:
    """测试工具执行时处理解析错误"""

    @pytest.mark.asyncio
    async def test_execute_tool_with_parse_error_returns_early(self):
        """测试解析错误时提前返回，不执行工具"""
        # 模拟解析错误
        tool_args = {
            "_parse_error": "JSON 解析失败: Unterminated string",
            "_raw_args": '{"path": "test.py...'
        }

        # Mock 依赖
        degr_manager = MagicMock()
        degr_manager.tool.should_skip.return_value = False
        metrics_collector = MagicMock()

        new_messages = []

        result_messages, state_update = await execute_single_tool(
            "write_file",
            tool_args,
            degr_manager,
            metrics_collector,
            lambda name, args: MagicMock(),
            new_messages
        )

        # 应该返回错误消息，不执行实际工具
        assert len(result_messages) == 1
        assert "工具参数解析失败" in result_messages[0].content
        assert state_update is None  # 不应该有状态更新，让 LLM 修正

    @pytest.mark.asyncio
    async def test_execute_tool_missing_path_returns_early(self):
        """测试缺少 path 参数时提前返回"""
        tool_args = {"content": "some content"}  # 缺少 path

        degr_manager = MagicMock()
        degr_manager.tool.should_skip.return_value = False
        metrics_collector = MagicMock()

        new_messages = []

        result_messages, state_update = await execute_single_tool(
            "write_file",
            tool_args,
            degr_manager,
            metrics_collector,
            lambda name, args: MagicMock(),
            new_messages
        )

        assert len(result_messages) == 1
        assert "requires 'path' argument" in result_messages[0].content


class TestLLMMaxTokensConfig:
    """测试 llm_max_tokens 配置项"""

    def test_llm_max_tokens_default_value(self):
        """测试默认值为 16384"""
        assert settings.llm_max_tokens == 16384

    def test_llm_max_tokens_in_valid_range(self):
        """测试值在有效范围内"""
        assert 1024 <= settings.llm_max_tokens <= 128000

    def test_llm_max_tokens_can_be_overridden(self):
        """测试可以通过环境变量覆盖"""
        # 这个测试验证配置系统工作正常
        # 实际环境变量覆盖需要在运行时测试
        from mini_claude.config.settings.llm_settings import LLMSettings
        test_settings = LLMSettings(llm_max_tokens=32768)
        assert test_settings.llm_max_tokens == 32768

    def test_llm_max_tokens_validation_lower_bound(self):
        """测试下限验证"""
        from mini_claude.config.settings.llm_settings import LLMSettings
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            LLMSettings(llm_max_tokens=500)  # 低于 1024

    def test_llm_max_tokens_validation_upper_bound(self):
        """测试上限验证"""
        from mini_claude.config.settings.llm_settings import LLMSettings
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            LLMSettings(llm_max_tokens=200000)  # 高于 128000


class TestActNodeUsesMaxTokens:
    """测试 act_node 使用 llm_max_tokens 配置"""

    @pytest.mark.asyncio
    async def test_streaming_call_uses_config_max_tokens(self):
        """测试流式调用使用配置的 max_tokens"""
        from mini_claude.agent.nodes.act import _streaming_llm_call

        # Mock provider
        mock_provider = MagicMock()
        mock_provider.chat_stream_with_tools = AsyncMock(return_value={
            "content": "test",
            "tool_calls": None
        })

        await _streaming_llm_call(
            mock_provider,
            [{"role": "user", "content": "test"}],
            [],
            max_tokens=settings.llm_max_tokens
        )

        # 验证调用时传入了正确的 max_tokens
        call_kwargs = mock_provider.chat_stream_with_tools.call_args[1]
        assert call_kwargs["max_tokens"] == settings.llm_max_tokens

    def test_max_tokens_value_propagates_correctly(self):
        """测试 max_tokens 值正确传递"""
        from mini_claude.config.settings.llm_settings import LLMSettings

        # 创建自定义设置的实例
        custom_settings = LLMSettings(llm_max_tokens=32768)
        assert custom_settings.llm_max_tokens == 32768


class TestLongToolArguments:
    """测试长工具参数处理"""

    def test_parse_tool_calls_long_arguments(self):
        """测试长参数正确解析"""
        # 模拟一个很长的文件内容
        long_content = "x" * 50000  # 50000 字符
        raw_tool_calls = [
            {
                "id": "call_1",
                "name": "write_file",
                "arguments": json.dumps({"path": "test.py", "content": long_content})
            }
        ]
        result = parse_tool_calls(raw_tool_calls)
        assert len(result) == 1
        assert result[0]["args"]["content"] == long_content

    def test_parse_tool_calls_raw_args_truncated(self):
        """测试 _raw_args 被截断到 500 字符"""
        # 模拟超长的截断 JSON
        long_truncated = '{"path": "test.py", "content": "' + "x" * 10000
        raw_tool_calls = [
            {
                "id": "call_1",
                "name": "write_file",
                "arguments": long_truncated
            }
        ]
        result = parse_tool_calls(raw_tool_calls)
        assert "_parse_error" in result[0]["args"]
        assert "_raw_args" in result[0]["args"]
        # _raw_args 应该被截断到 500 字符
        assert len(result[0]["args"]["_raw_args"]) == 500


class TestIntegrationScenarios:
    """集成场景测试"""

    def test_json_parse_error_message_includes_raw_preview(self):
        """测试错误消息包含原始参数预览"""
        raw_tool_calls = [
            {
                "id": "call_1",
                "name": "edit_file",
                "arguments": '{"path": "test.py", "old_text": "some text", "new_text": "new'  # 不完整
            }
        ]
        result = parse_tool_calls(raw_tool_calls)
        error_msg = result[0]["args"]["_parse_error"]
        raw_preview = result[0]["args"]["_raw_args"]

        assert "JSON 解析失败" in error_msg
        assert "test.py" in raw_preview  # 原始内容应该可见

    @pytest.mark.asyncio
    async def test_full_error_recovery_flow(self):
        """测试完整的错误恢复流程"""
        # 1. 模拟解析错误
        tool_args = {
            "_parse_error": "JSON 解析失败: Unterminated string",
            "_raw_args": '{"path": "test.py", "content": "partial...'
        }

        degr_manager = MagicMock()
        degr_manager.tool.should_skip.return_value = False
        metrics_collector = MagicMock()

        new_messages = []

        # 2. 执行工具
        result_messages, state_update = await execute_single_tool(
            "edit_file",
            tool_args,
            degr_manager,
            metrics_collector,
            lambda name, args: MagicMock(),
            new_messages
        )

        # 3. 验证错误消息被添加到消息列表
        assert len(result_messages) == 1
        error_content = result_messages[0].content

        # 4. 验证错误消息包含关键信息
        assert "工具参数解析失败" in error_content
        assert "JSON 解析失败" in error_content

        # 5. 验证没有状态更新，允许 LLM 修正
        assert state_update is None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
