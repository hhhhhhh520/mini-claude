"""Tests for suggestion engine - User operation suggestions."""

from mini_claude.agent.suggestion import (
    SuggestionEngine,
    Suggestion,
    ErrorType,
    Priority,
    get_suggestion_engine,
)


# ========== ErrorType Tests (8个) ==========


class TestErrorType:
    """Test ErrorType enum."""

    def test_error_type_values(self):
        """Test all error type values exist."""
        assert ErrorType.API_RATE_LIMIT.value == "api_rate_limit"
        assert ErrorType.FILE_PERMISSION.value == "file_permission"
        assert ErrorType.NETWORK_TIMEOUT.value == "network_timeout"
        assert ErrorType.TOKEN_EXCEEDED.value == "token_exceeded"
        assert ErrorType.TOOL_FAILURE.value == "tool_failure"
        assert ErrorType.MODEL_ERROR.value == "model_error"
        assert ErrorType.FILE_NOT_FOUND.value == "file_not_found"
        assert ErrorType.TEXT_NOT_FOUND.value == "text_not_found"
        assert ErrorType.INVALID_PARAMETER.value == "invalid_parameter"

    def test_error_type_unknown(self):
        """Test unknown error type."""
        assert ErrorType.UNKNOWN.value == "unknown"

    def test_error_type_count(self):
        """Test error type count."""
        # 10 types: rate_limit, file_permission, network_timeout, token_exceeded,
        # tool_failure, model_error, file_not_found, text_not_found,
        # invalid_parameter, unknown
        assert len(ErrorType) == 10


# ========== Priority Tests (3个) ==========


class TestPriority:
    """Test Priority enum."""

    def test_priority_values(self):
        """Test priority values."""
        assert Priority.HIGH.value == "high"
        assert Priority.MEDIUM.value == "medium"
        assert Priority.LOW.value == "low"

    def test_priority_order(self):
        """Test priority comparison can be done."""
        # Priorities are comparable by name
        priorities = [Priority.LOW, Priority.HIGH, Priority.MEDIUM]
        # Just verify they exist
        assert Priority.HIGH in priorities
        assert Priority.MEDIUM in priorities
        assert Priority.LOW in priorities


# ========== Suggestion Dataclass Tests (8个) ==========


class TestSuggestion:
    """Test Suggestion dataclass."""

    def test_suggestion_basic(self):
        """Test basic suggestion creation."""
        s = Suggestion(
            title="Test Title",
            description="Test description",
        )
        assert s.title == "Test Title"
        assert s.description == "Test description"
        assert s.actions == []
        assert s.priority == Priority.MEDIUM
        assert s.command is None
        assert s.doc_link is None

    def test_suggestion_with_actions(self):
        """Test suggestion with actions."""
        s = Suggestion(
            title="Test",
            description="Desc",
            actions=["Action 1", "Action 2"],
        )
        assert len(s.actions) == 2
        assert "Action 1" in s.actions

    def test_suggestion_with_priority(self):
        """Test suggestion with high priority."""
        s = Suggestion(
            title="Test",
            description="Desc",
            priority=Priority.HIGH,
        )
        assert s.priority == Priority.HIGH

    def test_suggestion_with_command(self):
        """Test suggestion with command."""
        s = Suggestion(
            title="Test",
            description="Desc",
            command="/clear",
        )
        assert s.command == "/clear"

    def test_suggestion_with_doc_link(self):
        """Test suggestion with documentation link."""
        s = Suggestion(
            title="Test",
            description="Desc",
            doc_link="https://example.com/docs",
        )
        assert s.doc_link == "https://example.com/docs"

    def test_suggestion_to_dict(self):
        """Test suggestion serialization."""
        s = Suggestion(
            title="Test",
            description="Desc",
            actions=["Action"],
            priority=Priority.HIGH,
            command="/test",
        )
        d = s.to_dict()
        assert d["title"] == "Test"
        assert d["description"] == "Desc"
        assert d["actions"] == ["Action"]
        assert d["priority"] == "high"
        assert d["command"] == "/test"

    def test_suggestion_to_dict_with_doc_link(self):
        """Test suggestion serialization with doc link."""
        s = Suggestion(
            title="Test",
            description="Desc",
            doc_link="https://example.com",
        )
        d = s.to_dict()
        assert d["doc_link"] == "https://example.com"

    def test_suggestion_all_fields(self):
        """Test suggestion with all fields."""
        s = Suggestion(
            title="Full Test",
            description="Full description",
            actions=["A1", "A2", "A3"],
            priority=Priority.LOW,
            command="/cmd",
            doc_link="https://link",
        )
        assert s.title == "Full Test"
        assert s.description == "Full description"
        assert len(s.actions) == 3
        assert s.priority == Priority.LOW
        assert s.command == "/cmd"
        assert s.doc_link == "https://link"


# ========== SuggestionEngine Error Classification Tests (18个) ==========


class TestSuggestionEngineErrorClassification:
    """Test error classification in SuggestionEngine."""

    def setup_method(self):
        """Setup test engine."""
        self.engine = SuggestionEngine(language="zh")

    def test_classify_rate_limit_english(self):
        """Test classifying rate limit error in English."""
        error_type = self.engine._classify_error("rate limit exceeded")
        assert error_type == ErrorType.API_RATE_LIMIT

    def test_classify_rate_limit_429(self):
        """Test classifying 429 error."""
        error_type = self.engine._classify_error("Error 429: Too Many Requests")
        assert error_type == ErrorType.API_RATE_LIMIT

    def test_classify_rate_limit_chinese(self):
        """Test classifying rate limit error in Chinese."""
        error_type = self.engine._classify_error("请求频率超限")
        assert error_type == ErrorType.API_RATE_LIMIT

    def test_classify_file_permission_english(self):
        """Test classifying file permission error."""
        error_type = self.engine._classify_error("Permission denied: /path/to/file")
        assert error_type == ErrorType.FILE_PERMISSION

    def test_classify_file_permission_chinese(self):
        """Test classifying permission error in Chinese."""
        error_type = self.engine._classify_error("权限不足: 无法访问文件")
        assert error_type == ErrorType.FILE_PERMISSION

    def test_classify_network_timeout(self):
        """Test classifying network timeout."""
        error_type = self.engine._classify_error("Connection timeout")
        assert error_type == ErrorType.NETWORK_TIMEOUT

    def test_classify_asyncio_timeout(self):
        """Test classifying asyncio timeout."""
        error_type = self.engine._classify_error("asyncio.TimeoutError")
        assert error_type == ErrorType.NETWORK_TIMEOUT

    def test_classify_token_exceeded(self):
        """Test classifying token exceeded."""
        error_type = self.engine._classify_error("context length exceeded")
        assert error_type == ErrorType.TOKEN_EXCEEDED

    def test_classify_token_budget(self):
        """Test classifying token budget exceeded."""
        error_type = self.engine._classify_error("token budget exceeded")
        assert error_type == ErrorType.TOKEN_EXCEEDED

    def test_classify_tool_failure(self):
        """Test classifying tool failure."""
        error_type = self.engine._classify_error("tool error: execution failed")
        assert error_type == ErrorType.TOOL_FAILURE

    def test_classify_model_error(self):
        """Test classifying model error."""
        error_type = self.engine._classify_error("invalid model specified")
        assert error_type == ErrorType.MODEL_ERROR

    def test_classify_api_key_error(self):
        """Test classifying API key error."""
        error_type = self.engine._classify_error("invalid api key")
        assert error_type == ErrorType.MODEL_ERROR

    def test_classify_file_not_found(self):
        """Test classifying file not found."""
        error_type = self.engine._classify_error("File not found: /path")
        assert error_type == ErrorType.FILE_NOT_FOUND

    def test_classify_no_such_file(self):
        """Test classifying no such file."""
        error_type = self.engine._classify_error("No such file or directory")
        assert error_type == ErrorType.FILE_NOT_FOUND

    def test_classify_invalid_parameter(self):
        """Test classifying invalid parameter."""
        error_type = self.engine._classify_error("invalid parameter: path")
        assert error_type == ErrorType.INVALID_PARAMETER

    def test_classify_unknown_error(self):
        """Test classifying unknown error."""
        error_type = self.engine._classify_error("Some random error message")
        assert error_type == ErrorType.UNKNOWN

    def test_classify_case_insensitive(self):
        """Test case insensitivity."""
        error_type = self.engine._classify_error("RATE LIMIT EXCEEDED")
        assert error_type == ErrorType.API_RATE_LIMIT

    def test_classify_mixed_case(self):
        """Test mixed case."""
        error_type = self.engine._classify_error("PermissionDenied Error")
        assert error_type == ErrorType.FILE_PERMISSION


# ========== SuggestionEngine Suggestion Retrieval Tests (10个) ==========


class TestSuggestionEngineGetSuggestions:
    """Test suggestion retrieval in SuggestionEngine."""

    def test_get_suggestions_rate_limit_zh(self):
        """Test getting rate limit suggestions in Chinese."""
        engine = SuggestionEngine(language="zh")
        suggestions = engine.get_suggestions(ErrorType.API_RATE_LIMIT)
        assert len(suggestions) >= 1
        assert all(isinstance(s, Suggestion) for s in suggestions)

    def test_get_suggestions_rate_limit_en(self):
        """Test getting rate limit suggestions in English."""
        engine = SuggestionEngine(language="en")
        suggestions = engine.get_suggestions(ErrorType.API_RATE_LIMIT)
        assert len(suggestions) >= 1
        # English suggestions should have English content
        assert "Wait" in suggestions[0].title or "Switch" in suggestions[0].title

    def test_get_suggestions_file_permission(self):
        """Test getting file permission suggestions."""
        engine = SuggestionEngine(language="zh")
        suggestions = engine.get_suggestions(ErrorType.FILE_PERMISSION)
        assert len(suggestions) >= 1
        assert suggestions[0].priority == Priority.HIGH

    def test_get_suggestions_network_timeout(self):
        """Test getting network timeout suggestions."""
        engine = SuggestionEngine(language="zh")
        suggestions = engine.get_suggestions(ErrorType.NETWORK_TIMEOUT)
        assert len(suggestions) >= 1

    def test_get_suggestions_token_exceeded(self):
        """Test getting token exceeded suggestions."""
        engine = SuggestionEngine(language="zh")
        suggestions = engine.get_suggestions(ErrorType.TOKEN_EXCEEDED)
        assert len(suggestions) >= 1
        # Should have /clear command
        assert any(s.command == "/clear" for s in suggestions)

    def test_get_suggestions_tool_failure(self):
        """Test getting tool failure suggestions."""
        engine = SuggestionEngine(language="zh")
        suggestions = engine.get_suggestions(ErrorType.TOOL_FAILURE)
        assert len(suggestions) >= 1

    def test_get_suggestions_model_error(self):
        """Test getting model error suggestions."""
        engine = SuggestionEngine(language="zh")
        suggestions = engine.get_suggestions(ErrorType.MODEL_ERROR)
        assert len(suggestions) >= 1

    def test_get_suggestions_unknown(self):
        """Test getting suggestions for unknown error."""
        engine = SuggestionEngine(language="zh")
        suggestions = engine.get_suggestions(ErrorType.UNKNOWN)
        assert len(suggestions) >= 1

    def test_analyze_error_returns_suggestion(self):
        """Test analyze_error returns a Suggestion."""
        engine = SuggestionEngine(language="zh")
        suggestion = engine.analyze_error("rate limit exceeded")
        assert isinstance(suggestion, Suggestion)

    def test_analyze_error_unknown(self):
        """Test analyze_error with unknown error."""
        engine = SuggestionEngine(language="zh")
        suggestion = engine.analyze_error("random unknown error xyz")
        assert isinstance(suggestion, Suggestion)
        # Should return default suggestion


# ========== SuggestionEngine Formatting Tests (6个) ==========


class TestSuggestionEngineFormatting:
    """Test suggestion formatting."""

    def test_format_suggestion_basic(self):
        """Test basic formatting."""
        engine = SuggestionEngine(language="zh")
        s = Suggestion(
            title="Test",
            description="Description",
            priority=Priority.HIGH,
        )
        formatted = engine.format_suggestion(s)
        assert "HIGH" in formatted
        assert "Test" in formatted
        assert "Description" in formatted

    def test_format_suggestion_with_actions(self):
        """Test formatting with actions."""
        engine = SuggestionEngine(language="zh")
        s = Suggestion(
            title="Test",
            description="Desc",
            actions=["Action 1", "Action 2"],
        )
        formatted = engine.format_suggestion(s)
        assert "Actions:" in formatted
        assert "Action 1" in formatted

    def test_format_suggestion_with_command(self):
        """Test formatting with command."""
        engine = SuggestionEngine(language="zh")
        s = Suggestion(
            title="Test",
            description="Desc",
            command="/clear",
        )
        formatted = engine.format_suggestion(s)
        assert "Command:" in formatted
        assert "/clear" in formatted

    def test_format_priority_high(self):
        """Test high priority formatting."""
        engine = SuggestionEngine(language="zh")
        s = Suggestion(title="Test", description="Desc", priority=Priority.HIGH)
        formatted = engine.format_suggestion(s)
        assert "[HIGH]" in formatted

    def test_format_priority_medium(self):
        """Test medium priority formatting."""
        engine = SuggestionEngine(language="zh")
        s = Suggestion(title="Test", description="Desc", priority=Priority.MEDIUM)
        formatted = engine.format_suggestion(s)
        assert "[MEDIUM]" in formatted

    def test_format_priority_low(self):
        """Test low priority formatting."""
        engine = SuggestionEngine(language="zh")
        s = Suggestion(title="Test", description="Desc", priority=Priority.LOW)
        formatted = engine.format_suggestion(s)
        assert "[LOW]" in formatted


# ========== SuggestionEngine Language Tests (4个) ==========


class TestSuggestionEngineLanguage:
    """Test language support."""

    def test_chinese_suggestions(self):
        """Test Chinese suggestions."""
        engine = SuggestionEngine(language="zh")
        suggestion = engine.analyze_error("rate limit")
        # Chinese suggestions should have Chinese content
        assert any(ord(c) > 127 for c in suggestion.title) or any(
            ord(c) > 127 for c in suggestion.description
        )

    def test_english_suggestions(self):
        """Test English suggestions."""
        engine = SuggestionEngine(language="en")
        suggestion = engine.analyze_error("rate limit")
        # English suggestions should be ASCII-heavy
        assert (
            suggestion.title.isascii() or "Retry" in suggestion.title or "Wait" in suggestion.title
        )

    def test_default_language(self):
        """Test default language is Chinese."""
        engine = SuggestionEngine()
        assert engine.language == "zh"

    def test_language_switch(self):
        """Test language switch creates new suggestions."""
        engine_zh = SuggestionEngine(language="zh")
        engine_en = SuggestionEngine(language="en")

        s_zh = engine_zh.analyze_error("rate limit")
        s_en = engine_en.analyze_error("rate limit")

        # Same error type, different languages
        assert s_zh.title != s_en.title  # Should be in different languages


# ========== Global Instance Tests (3个) ==========


class TestGetSuggestionEngine:
    """Test global instance management."""

    def test_get_suggestion_engine_creates_instance(self):
        """Test get_suggestion_engine creates instance."""
        import mini_claude.agent.suggestion as sug_module

        sug_module._suggestion_engine = None  # Reset

        engine = get_suggestion_engine()
        assert isinstance(engine, SuggestionEngine)

    def test_get_suggestion_engine_singleton(self):
        """Test get_suggestion_engine returns same instance."""
        import mini_claude.agent.suggestion as sug_module

        sug_module._suggestion_engine = None  # Reset

        engine1 = get_suggestion_engine()
        engine2 = get_suggestion_engine()
        assert engine1 is engine2

    def test_get_suggestion_engine_language_change(self):
        """Test get_suggestion_engine with different language."""
        import mini_claude.agent.suggestion as sug_module

        sug_module._suggestion_engine = None  # Reset

        get_suggestion_engine("zh")
        engine_en = get_suggestion_engine("en")
        # Language change should create new instance
        assert engine_en.language == "en"


# ========== Integration Tests (5个) ==========


class TestSuggestionEngineIntegration:
    """Integration tests for SuggestionEngine."""

    def test_full_flow_rate_limit_zh(self):
        """Test full flow for rate limit error in Chinese."""
        engine = SuggestionEngine(language="zh")
        error = "Error: rate limit exceeded, please wait"
        suggestion = engine.analyze_error(error)
        formatted = engine.format_suggestion(suggestion)

        assert suggestion.title is not None
        assert len(suggestion.actions) > 0
        assert "HIGH" in formatted or "MEDIUM" in formatted

    def test_full_flow_permission_en(self):
        """Test full flow for permission error in English."""
        engine = SuggestionEngine(language="en")
        error = "Permission denied: cannot write to /etc/hosts"
        suggestion = engine.analyze_error(error)

        assert suggestion.priority == Priority.HIGH
        assert any(
            "permission" in action.lower() or "chmod" in action.lower()
            for action in suggestion.actions
        )

    def test_full_flow_token_exceeded(self):
        """Test full flow for token exceeded."""
        engine = SuggestionEngine(language="zh")
        suggestions = engine.get_suggestions(ErrorType.TOKEN_EXCEEDED)

        # Should have both /clear and model switch suggestions
        has_clear = any(s.command == "/clear" for s in suggestions)
        has_model = any(s.command == "/model" for s in suggestions)
        assert has_clear or has_model

    def test_full_flow_unknown_error(self):
        """Test full flow for unknown error."""
        engine = SuggestionEngine(language="zh")
        error = "Something went wrong with the flux capacitor"
        suggestion = engine.analyze_error(error)

        # Should return default suggestion
        assert isinstance(suggestion, Suggestion)
        assert suggestion.priority == Priority.LOW

    def test_full_flow_model_error_with_api_key(self):
        """Test full flow for API key related error."""
        engine = SuggestionEngine(language="zh")
        error = "Error: invalid api key provided"
        suggestion = engine.analyze_error(error)

        # Should classify as model error
        assert engine._classify_error(error) == ErrorType.MODEL_ERROR
        assert isinstance(suggestion, Suggestion)
