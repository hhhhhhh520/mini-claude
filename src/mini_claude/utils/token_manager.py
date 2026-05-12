"""Token counting and budget management."""

from typing import List, Dict, Any, Optional, Callable
from dataclasses import dataclass
from enum import Enum
import time

try:
    import tiktoken

    TIKTOKEN_AVAILABLE = True
except ImportError:
    TIKTOKEN_AVAILABLE = False


class TokenLimitStrategy(str, Enum):
    """Token limit handling strategy."""

    WARN = "warn"  # Log warning when approaching limit
    TRUNCATE = "truncate"  # Truncate oldest messages
    SUMMARIZE = "summarize"  # Summarize old messages


# Circuit breaker configuration for summarization
CIRCUIT_BREAKER_MAX_FAILURES = 3  # Stop retrying after 3 consecutive failures
CIRCUIT_BREAKER_RESET_AFTER = 300  # Reset failure count after 300 seconds (5 minutes)


@dataclass
class ModelTokenLimits:
    """Token limits for different models."""

    context_window: int
    max_output: int
    encoding_name: str = "cl100k_base"  # Default for GPT-4/Claude


# Model token limits (context window, max output)
MODEL_LIMITS: Dict[str, ModelTokenLimits] = {
    # Claude models
    "claude-3-opus": ModelTokenLimits(200000, 4096, "cl100k_base"),
    "claude-3-sonnet": ModelTokenLimits(200000, 4096, "cl100k_base"),
    "claude-3-haiku": ModelTokenLimits(200000, 4096, "cl100k_base"),
    "claude-opus-4-7": ModelTokenLimits(200000, 16384, "cl100k_base"),
    "claude-sonnet-4-6": ModelTokenLimits(200000, 16384, "cl100k_base"),
    "claude-haiku-4-5": ModelTokenLimits(200000, 8192, "cl100k_base"),
    # OpenAI models
    "gpt-4": ModelTokenLimits(8192, 4096, "cl100k_base"),
    "gpt-4-32k": ModelTokenLimits(32768, 4096, "cl100k_base"),
    "gpt-4-turbo": ModelTokenLimits(128000, 4096, "cl100k_base"),
    "gpt-4o": ModelTokenLimits(128000, 16384, "cl100k_base"),
    "gpt-4o-mini": ModelTokenLimits(128000, 16384, "cl100k_base"),
    # DeepSeek models
    "deepseek-chat": ModelTokenLimits(128000, 8192, "cl100k_base"),
    "deepseek-coder": ModelTokenLimits(128000, 8192, "cl100k_base"),
    "deepseek-v4-flash": ModelTokenLimits(128000, 16384, "cl100k_base"),
    # Default fallback
    "default": ModelTokenLimits(128000, 4096, "cl100k_base"),
}


class TokenCounter:
    """Token counting and budget management."""

    def __init__(
        self,
        model: str = "deepseek-chat",
        budget_ratio: float = 0.65,  # Trigger compression earlier (was 0.8)
        warn_ratio: float = 0.55,  # Warn at 55% usage (was 0.75)
        strategy: TokenLimitStrategy = TokenLimitStrategy.WARN,
    ):
        self.model = model
        self.budget_ratio = budget_ratio
        self.warn_ratio = warn_ratio
        self.strategy = strategy

        # Get model limits
        self.limits = self._get_model_limits(model)
        self.token_budget = int(self.limits.context_window * budget_ratio)
        self.warn_threshold = int(self.limits.context_window * warn_ratio)

        # Initialize encoder
        self._encoder = None
        if TIKTOKEN_AVAILABLE:
            try:
                self._encoder = tiktoken.get_encoding(self.limits.encoding_name)
            except Exception:
                pass

        # Circuit breaker state for summarization
        self._summarize_failures: int = 0
        self._last_failure_time: float = 0
        self._circuit_open: bool = False

    def _get_model_limits(self, model: str) -> ModelTokenLimits:
        """Get token limits for a model."""
        model_lower = model.lower()

        # Direct match
        if model_lower in MODEL_LIMITS:
            return MODEL_LIMITS[model_lower]

        # Partial match
        for key, limits in MODEL_LIMITS.items():
            if key in model_lower or model_lower in key:
                return limits

        # Default
        return MODEL_LIMITS["default"]

    def _check_circuit_breaker(self) -> bool:
        """Check if circuit breaker allows summarization.

        Returns:
            True if summarization is allowed, False if circuit is open
        """
        current_time = time.time()

        # Reset circuit breaker after cooldown period
        if (
            self._circuit_open
            and (current_time - self._last_failure_time) > CIRCUIT_BREAKER_RESET_AFTER
        ):
            self._summarize_failures = 0
            self._circuit_open = False
            return True

        # Check if circuit is open
        if self._circuit_open:
            return False

        return True

    def _record_summarize_failure(self) -> None:
        """Record a summarization failure for circuit breaker."""
        self._summarize_failures += 1
        self._last_failure_time = time.time()

        if self._summarize_failures >= CIRCUIT_BREAKER_MAX_FAILURES:
            self._circuit_open = True

    def _record_summarize_success(self) -> None:
        """Record a successful summarization, reset failure count."""
        self._summarize_failures = 0
        self._circuit_open = False

    def get_circuit_breaker_status(self) -> Dict[str, Any]:
        """Get current circuit breaker status for debugging."""
        return {
            "failures": self._summarize_failures,
            "max_failures": CIRCUIT_BREAKER_MAX_FAILURES,
            "circuit_open": self._circuit_open,
            "last_failure_time": self._last_failure_time,
            "reset_after_seconds": CIRCUIT_BREAKER_RESET_AFTER,
        }

    def count_tokens(self, text: str) -> int:
        """Count tokens in text."""
        if self._encoder:
            return len(self._encoder.encode(text))
        else:
            # Fallback: approximate 4 chars per token
            return len(text) // 4

    def count_message_tokens(self, message: Dict[str, Any]) -> int:
        """Count tokens in a message (including role overhead)."""
        content = message.get("content", "")

        # Base tokens for message structure
        # Every message has role + content + formatting overhead
        tokens = 4  # <role>...</role><content>...</content> overhead

        if isinstance(content, str):
            tokens += self.count_tokens(content)
        elif isinstance(content, list):
            # Handle multi-modal content
            for part in content:
                if isinstance(part, dict):
                    if part.get("type") == "text":
                        tokens += self.count_tokens(part.get("text", ""))
                    elif part.get("type") == "image":
                        # Image tokens vary by size, estimate 85 tokens per image
                        tokens += 85

        # Tool calls add tokens
        if "tool_calls" in message:
            for tc in message["tool_calls"]:
                tokens += 4  # overhead
                if isinstance(tc, dict):
                    tokens += self.count_tokens(tc.get("function", {}).get("name", ""))
                    args = tc.get("function", {}).get("arguments", "")
                    if isinstance(args, str):
                        tokens += self.count_tokens(args)
                    elif isinstance(args, dict):
                        tokens += self.count_tokens(str(args))

        # Tool call ID adds tokens
        if "tool_call_id" in message:
            tokens += 4 + self.count_tokens(message["tool_call_id"])

        return tokens

    def count_messages_tokens(self, messages: List[Dict[str, Any]]) -> int:
        """Count total tokens in message list."""
        total = 3  # Every reply is primed with <im_start>assistant
        for msg in messages:
            total += self.count_message_tokens(msg)
        return total

    def get_usage_stats(
        self,
        messages: List[Dict[str, Any]],
        reserved_output: int = 4096,
    ) -> Dict[str, Any]:
        """Get token usage statistics."""
        current_tokens = self.count_messages_tokens(messages)
        available = self.limits.context_window - current_tokens - reserved_output
        usage_ratio = current_tokens / self.token_budget

        return {
            "model": self.model,
            "current_tokens": current_tokens,
            "token_budget": self.token_budget,
            "context_window": self.limits.context_window,
            "max_output": self.limits.max_output,
            "available_for_input": max(0, available),
            "reserved_output": reserved_output,
            "usage_ratio": usage_ratio,
            "usage_percent": round(usage_ratio * 100, 1),
            "is_over_budget": current_tokens > self.token_budget,
            "is_near_limit": current_tokens > self.warn_threshold,
            "should_warn": usage_ratio >= self.warn_ratio,
        }

    def check_budget(
        self,
        messages: List[Dict[str, Any]],
        reserved_output: int = 4096,
    ) -> Dict[str, Any]:
        """Check if messages fit within token budget.

        Returns:
            Dict with 'ok', 'reason', 'stats' keys
        """
        stats = self.get_usage_stats(messages, reserved_output)

        if stats["is_over_budget"]:
            return {
                "ok": False,
                "reason": f"Token budget exceeded: {stats['current_tokens']} > {stats['token_budget']}",
                "stats": stats,
                "action": self.strategy.value,
            }

        if stats["should_warn"]:
            return {
                "ok": True,
                "reason": f"Approaching token limit: {stats['usage_percent']}%",
                "stats": stats,
                "action": "warn",
            }

        return {
            "ok": True,
            "reason": "Within budget",
            "stats": stats,
            "action": None,
        }

    def truncate_messages(
        self,
        messages: List[Dict[str, Any]],
        keep_first: int = 1,  # Keep system message
        keep_last: int = 4,  # Keep recent context
    ) -> List[Dict[str, Any]]:
        """Truncate messages to fit within budget.

        Args:
            messages: List of messages
            keep_first: Number of messages to keep from start (system prompt)
            keep_last: Number of messages to keep from end (recent context)

        Returns:
            Truncated message list
        """
        if len(messages) <= keep_first + keep_last:
            # Even if small list, check if content fits
            stats = self.get_usage_stats(messages)
            if not stats["is_over_budget"]:
                return messages

        # Keep first and last, remove middle
        first = messages[:keep_first]
        last = messages[-keep_last:] if len(messages) > keep_first else []

        # Check if truncated fits
        truncated = first + last
        stats = self.get_usage_stats(truncated)

        if not stats["is_over_budget"]:
            return truncated

        # Still over budget, reduce keep_last
        while keep_last > 1 and stats["is_over_budget"]:
            keep_last -= 1
            last = messages[-keep_last:] if len(messages) > keep_last else []
            truncated = first + last
            stats = self.get_usage_stats(truncated)

        # If still over budget, truncate content of individual messages
        if stats["is_over_budget"] and truncated:
            # Truncate each message content to fit
            max_tokens_per_msg = self.token_budget // len(truncated)
            result = []
            for msg in truncated:
                content = msg.get("content", "")
                if isinstance(content, str) and len(content) > max_tokens_per_msg * 4:
                    # Truncate content to fit
                    max_chars = max_tokens_per_msg * 4
                    truncated_content = content[:max_chars] + "\n...[truncated]..."
                    result.append({**msg, "content": truncated_content})
                else:
                    result.append(msg)
            return result

        return truncated

    def update_model(self, model: str) -> None:
        """Update model and recalculate limits."""
        self.model = model
        self.limits = self._get_model_limits(model)
        self.token_budget = int(self.limits.context_window * self.budget_ratio)
        self.warn_threshold = int(self.limits.context_window * self.warn_ratio)

        # Update encoder if encoding changed
        if TIKTOKEN_AVAILABLE:
            try:
                self._encoder = tiktoken.get_encoding(self.limits.encoding_name)
            except Exception:
                pass

    async def summarize_messages(
        self,
        messages: List[Dict[str, Any]],
        llm_chat_func: Callable,
        keep_first: int = 1,  # Keep system message
        keep_last: int = 4,  # Keep recent context
        max_summary_tokens: int = 500,
        return_summary_only: bool = False,
    ) -> tuple[List[Dict[str, Any]], Optional[str]]:
        """Summarize old messages to reduce token count.

        This method keeps the first message (system prompt) and last few messages
        (recent context), then summarizes the middle messages into a single summary.

        Args:
            messages: List of messages to summarize
            llm_chat_func: Async function to call LLM for summarization
                          Signature: async (messages: List[Dict]) -> Dict
            keep_first: Number of messages to keep from start (system prompt)
            keep_last: Number of messages to keep from end (recent context)
            max_summary_tokens: Maximum tokens for the summary
            return_summary_only: If True, only return the summary text (no compressed messages)

        Returns:
            Tuple of (compressed message list, summary text or None)
        """
        if len(messages) <= keep_first + keep_last:
            # Not enough messages to summarize
            return messages, None

        # Check circuit breaker before attempting summarization
        if not self._check_circuit_breaker():
            # Circuit is open, fall back to truncation immediately
            print(
                f"[WARN] Circuit breaker open - summarization disabled after {self._summarize_failures} failures"
            )
            return self.truncate_messages(
                messages, keep_first=keep_first, keep_last=keep_last
            ), None

        # Split messages
        first = messages[:keep_first]
        middle = messages[keep_first:-keep_last]
        last = messages[-keep_last:]

        if not middle:
            return first + last, None

        # Build summarization prompt
        middle_text = self._format_messages_for_summary(middle)

        summary_prompt = f"""请将以下对话历史压缩成一个简洁的摘要，保留关键信息：

{middle_text}

要求：
1. 保留用户的主要请求和目标
2. 保留已完成的操作和结果
3. 保留重要的决策和结论
4. 省略冗余的细节和中间步骤
5. 摘要长度控制在 {max_summary_tokens} tokens 以内

直接输出摘要内容，不要添加任何前缀或解释。"""

        try:
            # Call LLM to generate summary
            response = await llm_chat_func(
                messages=[{"role": "user", "content": summary_prompt}],
                temperature=0.3,
                max_tokens=max_summary_tokens,
            )

            # Extract summary from response
            if hasattr(response, "choices"):
                summary = response.choices[0].message.content
            elif isinstance(response, dict):
                summary = response.get("choices", [{}])[0].get("message", {}).get("content", "")
            else:
                summary = str(response)

            # Create summary message
            summary_message = {
                "role": "assistant",
                "content": f"[历史对话摘要]\n{summary}",
            }

            result = first + [summary_message] + last

            # Record success - reset circuit breaker
            self._record_summarize_success()

            # Verify the result fits within budget
            stats = self.get_usage_stats(result)
            if stats["is_over_budget"]:
                # Still over budget, truncate further
                return self.truncate_messages(
                    result, keep_first=keep_first, keep_last=keep_last - 1
                ), summary

            return result, summary

        except Exception as e:
            # Record failure for circuit breaker
            self._record_summarize_failure()

            # If summarization fails, fall back to truncation
            import traceback

            print(
                f"[WARN] Summarization failed (attempt {self._summarize_failures}/{CIRCUIT_BREAKER_MAX_FAILURES}): {e}"
            )
            print(f"[DEBUG] Traceback: {traceback.format_exc()}")
            return self.truncate_messages(
                messages, keep_first=keep_first, keep_last=keep_last
            ), None

    def _format_messages_for_summary(self, messages: List[Dict[str, Any]]) -> str:
        """Format messages into text for summarization."""
        lines = []
        for msg in messages:
            role = msg.get("role", "unknown")
            content = msg.get("content", "")

            # Handle different content types
            if isinstance(content, list):
                # Multi-modal content - extract text parts
                text_parts = []
                for part in content:
                    if isinstance(part, dict) and part.get("type") == "text":
                        text_parts.append(part.get("text", ""))
                    elif isinstance(part, str):
                        text_parts.append(part)
                content = " ".join(text_parts)
            elif not isinstance(content, str):
                content = str(content)

            # Truncate very long messages
            if len(content) > 1000:
                content = content[:1000] + "...[已截断]"

            # Handle tool calls
            tool_calls = msg.get("tool_calls")
            if tool_calls:
                tool_names = [tc.get("function", {}).get("name", "unknown") for tc in tool_calls]
                content += f" [工具调用: {', '.join(tool_names)}]"

            # Handle tool results
            if role == "tool":
                tool_name = msg.get("name", "unknown")
                lines.append(f"[工具结果 {tool_name}]: {content[:200]}...")
            else:
                role_name = {"user": "用户", "assistant": "助手", "system": "系统"}.get(role, role)
                lines.append(f"{role_name}: {content}")

        return "\n".join(lines)


# Global token counter instance
_token_counter: Optional[TokenCounter] = None


def get_token_counter(model: str = "deepseek-chat") -> TokenCounter:
    """Get or create global token counter.

    This function provides backward compatibility with existing code.
    New code should prefer ApplicationContext.token_counter.

    Args:
        model: Model name for tokenization.

    Returns:
        Singleton TokenCounter instance.
    """
    global _token_counter
    if _token_counter is None or _token_counter.model != model:
        # Try to use ApplicationContext first
        try:
            from mini_claude.context import get_context

            ctx = get_context()
            if ctx._token_counter.is_initialized():
                cached = ctx.token_counter
                if cached.model == model:
                    _token_counter = cached
                else:
                    _token_counter = TokenCounter(model=model)
                    ctx.token_counter = _token_counter
            else:
                _token_counter = TokenCounter(model=model)
                ctx.token_counter = _token_counter
        except ImportError:
            _token_counter = TokenCounter(model=model)
    return _token_counter


def reset_token_counter() -> None:
    """Reset the global token counter (for testing)."""
    global _token_counter
    _token_counter = None
    # Also reset in context
    try:
        from mini_claude.context import get_context

        ctx = get_context()
        ctx._token_counter.reset()
    except ImportError:
        pass


def count_tokens(text: str, model: str = "deepseek-chat") -> int:
    """Convenience function to count tokens."""
    return get_token_counter(model).count_tokens(text)


def count_messages_tokens(
    messages: List[Dict[str, Any]],
    model: str = "deepseek-chat",
) -> int:
    """Convenience function to count message tokens."""
    return get_token_counter(model).count_messages_tokens(messages)
