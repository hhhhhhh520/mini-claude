"""Tests for token_manager module."""

import pytest
from unittest.mock import patch, MagicMock, AsyncMock

from mini_claude.utils.token_manager import (
    TokenCounter,
    TokenLimitStrategy,
    ModelTokenLimits,
    MODEL_LIMITS,
    get_token_counter,
    count_tokens,
    count_messages_tokens,
)


class TestModelTokenLimits:
    """Test model token limits configuration."""

    def test_model_limits_exist(self):
        """Test that essential models have limits defined."""
        essential_models = [
            "deepseek-chat",
            "gpt-4o",
            "claude-3-opus",
        ]
        for model in essential_models:
            assert model in MODEL_LIMITS, f"Missing limits for {model}"

    def test_default_limits_exist(self):
        """Test that default limits exist."""
        assert "default" in MODEL_LIMITS
        default = MODEL_LIMITS["default"]
        assert default.context_window > 0
        assert default.max_output > 0


class TestTokenCounter:
    """Test TokenCounter class."""

    def test_init_default_model(self):
        """Test initialization with default model."""
        counter = TokenCounter()
        assert counter.model == "deepseek-chat"
        assert counter.token_budget > 0
        assert counter.warn_threshold > 0

    def test_init_custom_model(self):
        """Test initialization with custom model."""
        counter = TokenCounter(model="gpt-4o")
        assert counter.model == "gpt-4o"
        assert counter.limits.context_window == 128000

    def test_init_custom_ratios(self):
        """Test initialization with custom ratios."""
        counter = TokenCounter(budget_ratio=0.9, warn_ratio=0.8)
        assert counter.budget_ratio == 0.9
        assert counter.warn_ratio == 0.8

    def test_count_tokens_fallback(self):
        """Test token counting without tiktoken (fallback)."""
        with patch("mini_claude.utils.token_manager.TIKTOKEN_AVAILABLE", False):
            counter = TokenCounter()
            counter._encoder = None

            # Fallback: ~4 chars per token
            text = "Hello world"  # 11 chars -> ~2-3 tokens
            tokens = counter.count_tokens(text)
            assert tokens >= 0

    def test_count_message_tokens_simple(self):
        """Test counting tokens in a simple message."""
        counter = TokenCounter()
        message = {"role": "user", "content": "Hello world"}
        tokens = counter.count_message_tokens(message)
        assert tokens > 0

    def test_count_message_tokens_with_tool_calls(self):
        """Test counting tokens in a message with tool calls."""
        counter = TokenCounter()
        message = {
            "role": "assistant",
            "content": "I will help you.",
            "tool_calls": [
                {
                    "id": "call_123",
                    "function": {
                        "name": "write_file",
                        "arguments": '{"path": "test.py", "content": "print(1)"}'
                    }
                }
            ]
        }
        tokens = counter.count_message_tokens(message)
        assert tokens > 0

    def test_count_messages_tokens(self):
        """Test counting tokens in message list."""
        counter = TokenCounter()
        messages = [
            {"role": "system", "content": "You are a helpful assistant."},
            {"role": "user", "content": "Hello"},
            {"role": "assistant", "content": "Hi there!"},
        ]
        total = counter.count_messages_tokens(messages)
        assert total > 0

        # Total should be greater than sum of individual messages
        # (due to message structure overhead)
        individual_sum = sum(counter.count_message_tokens(m) for m in messages)
        assert total >= individual_sum

    def test_get_usage_stats(self):
        """Test usage statistics calculation."""
        counter = TokenCounter(model="deepseek-chat")
        messages = [
            {"role": "user", "content": "Hello"},
            {"role": "assistant", "content": "Hi!"},
        ]

        stats = counter.get_usage_stats(messages)

        assert stats["model"] == "deepseek-chat"
        assert stats["current_tokens"] > 0
        assert stats["token_budget"] > 0
        assert stats["context_window"] == 128000
        assert stats["usage_ratio"] >= 0
        assert stats["usage_percent"] >= 0
        assert isinstance(stats["is_over_budget"], bool)
        assert isinstance(stats["is_near_limit"], bool)

    def test_check_budget_ok(self):
        """Test budget check when within limits."""
        counter = TokenCounter()
        messages = [{"role": "user", "content": "Hello"}]

        result = counter.check_budget(messages)

        assert result["ok"] is True
        assert "stats" in result

    def test_check_budget_exceeded(self):
        """Test budget check when over limit."""
        counter = TokenCounter(budget_ratio=0.001)  # Very small budget
        messages = [
            {"role": "user", "content": "A" * 10000},
        ]

        result = counter.check_budget(messages)

        # With very small budget, should be over
        assert result["ok"] is False or result["stats"]["is_over_budget"]

    def test_truncate_messages(self):
        """Test message truncation."""
        counter = TokenCounter()
        messages = [
            {"role": "system", "content": "System prompt"},
            {"role": "user", "content": "Message 1"},
            {"role": "assistant", "content": "Response 1"},
            {"role": "user", "content": "Message 2"},
            {"role": "assistant", "content": "Response 2"},
        ]

        truncated = counter.truncate_messages(messages, keep_first=1, keep_last=2)

        # Should keep system + last 2 messages
        assert len(truncated) <= 3
        assert truncated[0]["role"] == "system"

    def test_truncate_messages_small_list(self):
        """Test truncation with small message list."""
        counter = TokenCounter()
        messages = [
            {"role": "user", "content": "Hello"},
        ]

        truncated = counter.truncate_messages(messages)

        # Should not modify small lists
        assert len(truncated) == 1

    def test_update_model(self):
        """Test updating model."""
        counter = TokenCounter(model="deepseek-chat")
        assert counter.limits.context_window == 128000

        counter.update_model("gpt-4o")
        assert counter.model == "gpt-4o"
        assert counter.limits.context_window == 128000

    def test_partial_model_match(self):
        """Test partial model name matching."""
        counter = TokenCounter(model="claude-3-opus-20240229")
        # Should match claude-3-opus
        assert counter.limits.context_window == 200000


class TestGlobalFunctions:
    """Test global convenience functions."""

    def test_get_token_counter_singleton(self):
        """Test that get_token_counter returns same instance."""
        counter1 = get_token_counter()
        counter2 = get_token_counter()

        assert counter1 is counter2

    def test_get_token_counter_different_models(self):
        """Test that different models create new counter."""
        import mini_claude.utils.token_manager as tm
        tm._token_counter = None  # Reset

        counter1 = get_token_counter("deepseek-chat")
        counter2 = get_token_counter("gpt-4o")

        assert counter1 is not counter2
        assert counter2.model == "gpt-4o"

    def test_count_tokens_function(self):
        """Test count_tokens convenience function."""
        tokens = count_tokens("Hello world")
        assert tokens >= 0

    def test_count_messages_tokens_function(self):
        """Test count_messages_tokens convenience function."""
        messages = [
            {"role": "user", "content": "Hello"},
        ]
        tokens = count_messages_tokens(messages)
        assert tokens > 0


class TestTokenLimitStrategy:
    """Test token limit strategies."""

    def test_strategy_enum_values(self):
        """Test strategy enum values."""
        assert TokenLimitStrategy.WARN.value == "warn"
        assert TokenLimitStrategy.TRUNCATE.value == "truncate"
        assert TokenLimitStrategy.SUMMARIZE.value == "summarize"

    def test_strategy_in_counter(self):
        """Test strategy is stored in counter."""
        counter = TokenCounter(strategy=TokenLimitStrategy.TRUNCATE)
        assert counter.strategy == TokenLimitStrategy.TRUNCATE


class TestEdgeCases:
    """Test edge cases."""

    def test_empty_message(self):
        """Test counting empty message."""
        counter = TokenCounter()
        tokens = counter.count_message_tokens({})
        assert tokens >= 4  # Minimum overhead

    def test_empty_message_list(self):
        """Test counting empty message list."""
        counter = TokenCounter()
        tokens = counter.count_messages_tokens([])
        assert tokens == 3  # Just the base overhead

    def test_multimodal_content(self):
        """Test counting multimodal content."""
        counter = TokenCounter()
        message = {
            "role": "user",
            "content": [
                {"type": "text", "text": "What's in this image?"},
                {"type": "image", "image_url": "http://example.com/image.png"},
            ]
        }
        tokens = counter.count_message_tokens(message)
        assert tokens > 0

    def test_very_long_text(self):
        """Test counting very long text."""
        counter = TokenCounter()
        text = "A" * 100000
        tokens = counter.count_tokens(text)
        assert tokens > 0

    def test_unicode_text(self):
        """Test counting unicode text."""
        counter = TokenCounter()
        text = "你好世界 🌍"
        tokens = counter.count_tokens(text)
        assert tokens >= 0


class TestTokenBudgetIntegration:
    """Test token budget integration with settings."""

    def test_settings_token_config(self):
        """Test token budget settings are loaded."""
        from mini_claude.config.settings import settings

        assert hasattr(settings, "token_budget_ratio")
        assert hasattr(settings, "token_warn_ratio")
        assert hasattr(settings, "token_strategy")
        assert hasattr(settings, "token_reserved_output")

        assert 0 < settings.token_budget_ratio <= 1
        assert 0 < settings.token_warn_ratio <= 1
        assert settings.token_strategy in ["warn", "truncate", "summarize"]
        assert settings.token_reserved_output > 0

    def test_token_counter_with_settings(self):
        """Test token counter respects settings."""
        from mini_claude.config.settings import settings

        counter = get_token_counter(settings.default_model)
        counter.budget_ratio = settings.token_budget_ratio
        counter.warn_ratio = settings.token_warn_ratio

        # Verify ratios are applied
        expected_budget = int(counter.limits.context_window * settings.token_budget_ratio)
        assert counter.token_budget == expected_budget

    def test_budget_check_with_reserved_output(self):
        """Test budget check with reserved output tokens."""
        from mini_claude.config.settings import settings

        counter = get_token_counter(settings.default_model)
        messages = [{"role": "user", "content": "Hello world"}]

        result = counter.check_budget(messages, reserved_output=settings.token_reserved_output)

        assert "stats" in result
        assert result["stats"]["reserved_output"] == settings.token_reserved_output

    def test_truncate_strategy_applied(self):
        """Test truncate strategy is applied when over budget."""
        counter = TokenCounter(
            model="deepseek-chat",
            budget_ratio=0.001,  # Very small budget
            strategy=TokenLimitStrategy.TRUNCATE,
        )

        # Create messages that exceed budget
        messages = [
            {"role": "system", "content": "System prompt"},
            {"role": "user", "content": "A" * 10000},
            {"role": "assistant", "content": "B" * 10000},
            {"role": "user", "content": "C" * 10000},
            {"role": "assistant", "content": "D" * 10000},
        ]

        budget_check = counter.check_budget(messages)
        assert not budget_check["ok"]

        # Truncate should reduce message count
        truncated = counter.truncate_messages(messages)
        assert len(truncated) < len(messages)


class TestSummarizeMessages:
    """Test message summarization functionality."""

    @pytest.mark.asyncio
    async def test_summarize_messages_basic(self):
        """Test basic message summarization."""
        counter = TokenCounter(model="deepseek-chat")

        messages = [
            {"role": "system", "content": "System prompt"},
            {"role": "user", "content": "Create a Python file"},
            {"role": "assistant", "content": "I will create the file"},
            {"role": "user", "content": "Add some functions"},
            {"role": "assistant", "content": "Added functions"},
            {"role": "user", "content": "Run the file"},
            {"role": "assistant", "content": "Running..."},
        ]

        # Mock LLM response
        async def mock_llm_chat(messages, **kwargs):
            return {
                "choices": [
                    {"message": {"content": "用户请求创建Python文件并添加函数，已完成。"}}
                ]
            }

        summarized, summary_text = await counter.summarize_messages(
            messages,
            llm_chat_func=mock_llm_chat,
            keep_first=1,
            keep_last=2,
        )

        # Should have: system + summary + last 2
        assert len(summarized) <= 4
        assert summarized[0]["role"] == "system"
        assert "[历史对话摘要]" in summarized[1]["content"]
        assert summary_text is not None

    @pytest.mark.asyncio
    async def test_summarize_messages_small_list(self):
        """Test summarization with small message list."""
        counter = TokenCounter()

        messages = [
            {"role": "system", "content": "System"},
            {"role": "user", "content": "Hello"},
        ]

        async def mock_llm_chat(messages, **kwargs):
            return {"choices": [{"message": {"content": "Summary"}}]}

        summarized, summary_text = await counter.summarize_messages(
            messages,
            llm_chat_func=mock_llm_chat,
        )

        # Small list should not be modified
        assert len(summarized) == len(messages)
        assert summary_text is None

    @pytest.mark.asyncio
    async def test_summarize_messages_with_tool_calls(self):
        """Test summarization with tool calls."""
        counter = TokenCounter()

        messages = [
            {"role": "system", "content": "System"},
            {"role": "user", "content": "Create file"},
            {"role": "assistant", "content": "", "tool_calls": [
                {"function": {"name": "write_file", "arguments": '{"path": "test.py"}'}}
            ]},
            {"role": "tool", "name": "write_file", "content": "File created"},
            {"role": "user", "content": "Now run it"},
            {"role": "assistant", "content": "Running"},
        ]

        async def mock_llm_chat(messages, **kwargs):
            return {"choices": [{"message": {"content": "创建了文件并运行"}}]}

        summarized, summary_text = await counter.summarize_messages(
            messages,
            llm_chat_func=mock_llm_chat,
            keep_first=1,
            keep_last=2,
        )

        # Should include tool call info in summary
        assert len(summarized) <= 4
        assert summarized[0]["role"] == "system"
        assert summary_text is not None

    @pytest.mark.asyncio
    async def test_summarize_messages_llm_failure(self):
        """Test fallback when LLM fails."""
        counter = TokenCounter()

        messages = [
            {"role": "system", "content": "System"},
            {"role": "user", "content": "A" * 1000},
            {"role": "assistant", "content": "B" * 1000},
            {"role": "user", "content": "C" * 1000},
            {"role": "assistant", "content": "D" * 1000},
        ]

        # Mock LLM that raises exception
        async def mock_llm_chat(messages, **kwargs):
            raise Exception("LLM error")

        summarized, summary_text = await counter.summarize_messages(
            messages,
            llm_chat_func=mock_llm_chat,
        )

        # Should fall back to truncation
        assert len(summarized) <= len(messages)
        assert summary_text is None  # LLM failed, no summary

    @pytest.mark.asyncio
    async def test_summarize_messages_over_budget_after_summary(self):
        """Test truncation when summary still exceeds budget."""
        counter = TokenCounter(budget_ratio=0.001)  # Very small budget

        messages = [
            {"role": "system", "content": "System"},
            {"role": "user", "content": "A" * 10000},
            {"role": "assistant", "content": "B" * 10000},
            {"role": "user", "content": "C" * 10000},
            {"role": "assistant", "content": "D" * 10000},
        ]

        async def mock_llm_chat(messages, **kwargs):
            return {"choices": [{"message": {"content": "Long summary " * 100}}]}

        summarized, summary_text = await counter.summarize_messages(
            messages,
            llm_chat_func=mock_llm_chat,
        )

        # Should fall back to truncation due to still being over budget
        assert len(summarized) <= len(messages)

    def test_format_messages_for_summary(self):
        """Test message formatting for summary."""
        counter = TokenCounter()

        messages = [
            {"role": "user", "content": "Hello"},
            {"role": "assistant", "content": "Hi there"},
            {"role": "tool", "name": "write_file", "content": "Success"},
        ]

        formatted = counter._format_messages_for_summary(messages)

        assert "用户" in formatted
        assert "助手" in formatted
        assert "工具结果" in formatted

    def test_format_messages_with_tool_calls(self):
        """Test formatting messages with tool calls."""
        counter = TokenCounter()

        messages = [
            {"role": "assistant", "content": "", "tool_calls": [
                {"function": {"name": "write_file"}},
                {"function": {"name": "read_file"}},
            ]},
        ]

        formatted = counter._format_messages_for_summary(messages)

        assert "工具调用" in formatted
        assert "write_file" in formatted
        assert "read_file" in formatted

    def test_format_messages_truncation(self):
        """Test truncation of very long messages."""
        counter = TokenCounter()

        messages = [
            {"role": "user", "content": "A" * 2000},
        ]

        formatted = counter._format_messages_for_summary(messages)

        # Should be truncated to ~1000 chars
        assert len(formatted) < 2000
        assert "已截断" in formatted
