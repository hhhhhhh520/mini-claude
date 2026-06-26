"""Tests for edit_file retry scenarios.

This module tests consecutive file editing scenarios where:
1. First edit succeeds but second edit with stale old_text fails
2. User needs to read file to get current content before retrying
3. Error messages should provide helpful guidance
4. SuggestionEngine should recognize text not found errors

Created for SUB-004: Testing consecutive file modification retry scenarios.
"""

import pytest
import os
import tempfile
from pathlib import Path

from mini_claude.tools.file_ops import EditFileTool, ReadFileTool, WriteFileTool
from mini_claude.agent.suggestion import SuggestionEngine, ErrorType
from mini_claude.config.settings import settings as config_settings


class TestEditFileRetry:
    """Test edit_file retry scenarios for consecutive file modifications."""

    @pytest.fixture
    def temp_file(self):
        """Create a temporary file for testing."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
            f.write("Initial content\n")
            filepath = f.name
        yield filepath
        # Cleanup
        if os.path.exists(filepath):
            os.unlink(filepath)

    @pytest.fixture
    def temp_dir(self):
        """Create a temporary directory for testing."""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield tmpdir

    @pytest.fixture
    def mock_workspace(self, temp_dir):
        """Mock the workspace root to the temp directory."""
        # Normalize path to resolve Windows 8.3 short names (RUNNER~1 -> runneradmin)
        normalized = str(Path(temp_dir).resolve())
        original_workspace = config_settings.workspace_root
        config_settings.workspace_root = normalized
        try:
            yield normalized
        finally:
            config_settings.workspace_root = original_workspace

    # ========== Test 1: Consecutive Edits - Second Fails ==========

    @pytest.mark.asyncio
    async def test_consecutive_edits_second_fails(self, temp_dir, mock_workspace):
        """Test that second edit with stale old_text fails.

        Scenario:
        1. Create file with initial content
        2. First edit succeeds
        3. Second edit with stale old_text fails

        This verifies that using outdated old_text correctly fails
        instead of silently succeeding.
        """
        write_tool = WriteFileTool()
        edit_tool = EditFileTool()
        filepath = os.path.join(temp_dir, "test_retry.txt")

        # Setup: Create file with initial content
        await write_tool.execute(path=filepath, content="Initial content\n")

        # First edit succeeds
        result1 = await edit_tool.execute(
            path=filepath, old_text="Initial content", new_text="Updated content"
        )
        assert "Successfully" in result1, f"First edit should succeed: {result1}"

        # Second edit with stale old_text should fail
        result2 = await edit_tool.execute(
            path=filepath, old_text="Initial content", new_text="New content"
        )
        assert "Error" in result2, f"Second edit should fail: {result2}"
        assert "Text not found" in result2 or "not found" in result2.lower(), (
            f"Error should indicate text not found: {result2}"
        )

    @pytest.mark.asyncio
    async def test_consecutive_edits_with_correct_content(self, temp_dir, mock_workspace):
        """Test that consecutive edits with correct old_text succeed.

        This is the positive case where the user uses the correct content
        after each modification.
        """
        write_tool = WriteFileTool()
        edit_tool = EditFileTool()
        read_tool = ReadFileTool()
        filepath = os.path.join(temp_dir, "test_correct.txt")

        # Setup
        await write_tool.execute(path=filepath, content="Version 1\n")

        # First edit
        result1 = await edit_tool.execute(path=filepath, old_text="Version 1", new_text="Version 2")
        assert "Successfully" in result1

        # Verify content changed
        content1 = await read_tool.execute(path=filepath)
        assert "Version 2" in content1

        # Second edit with correct old_text
        result2 = await edit_tool.execute(path=filepath, old_text="Version 2", new_text="Version 3")
        assert "Successfully" in result2

        # Verify final content
        content2 = await read_tool.execute(path=filepath)
        assert "Version 3" in content2

    # ========== Test 2: Edit Fail -> Read -> Edit Succeed ==========

    @pytest.mark.asyncio
    async def test_edit_fail_then_read_then_succeed(self, temp_dir, mock_workspace):
        """Test the typical retry flow: edit fails, read file, edit succeeds.

        Scenario:
        1. Edit with stale old_text fails
        2. Read file to get current content
        3. Retry edit with correct old_text succeeds
        """
        write_tool = WriteFileTool()
        edit_tool = EditFileTool()
        read_tool = ReadFileTool()
        filepath = os.path.join(temp_dir, "test_flow.txt")

        # Setup: Create and modify file
        await write_tool.execute(path=filepath, content="Original content\n")
        await edit_tool.execute(
            path=filepath, old_text="Original content", new_text="Modified content"
        )

        # Attempt edit with stale old_text - should fail
        result_fail = await edit_tool.execute(
            path=filepath, old_text="Original content", new_text="New content"
        )
        assert "Error" in result_fail, "Edit with stale content should fail"

        # Read file to get current content
        current_content = await read_tool.execute(path=filepath)
        assert "Modified content" in current_content, (
            f"Read should return current content: {current_content}"
        )

        # Retry edit with correct old_text - should succeed
        result_success = await edit_tool.execute(
            path=filepath, old_text="Modified content", new_text="New content"
        )
        assert "Successfully" in result_success, (
            f"Edit with correct content should succeed: {result_success}"
        )

        # Verify final state
        final_content = await read_tool.execute(path=filepath)
        assert "New content" in final_content

    @pytest.mark.asyncio
    async def test_multiple_retry_attempts(self, temp_dir, mock_workspace):
        """Test multiple failed attempts before success.

        This tests a scenario where the user might try multiple wrong
        old_text values before reading and succeeding.
        """
        write_tool = WriteFileTool()
        edit_tool = EditFileTool()
        read_tool = ReadFileTool()
        filepath = os.path.join(temp_dir, "test_multi.txt")

        # Setup
        await write_tool.execute(path=filepath, content="Content A\n")

        # First modification
        await edit_tool.execute(path=filepath, old_text="Content A", new_text="Content B")

        # Multiple failed attempts
        result1 = await edit_tool.execute(path=filepath, old_text="Content A", new_text="Content C")
        assert "Error" in result1

        result2 = await edit_tool.execute(
            path=filepath, old_text="Wrong text", new_text="Content C"
        )
        assert "Error" in result2

        # Finally read and succeed
        current = await read_tool.execute(path=filepath)
        assert "Content B" in current

        result3 = await edit_tool.execute(path=filepath, old_text="Content B", new_text="Content C")
        assert "Successfully" in result3

    # ========== Test 3: Error Message Contains Content Preview ==========

    @pytest.mark.asyncio
    async def test_error_message_contains_content_preview(self, temp_dir, mock_workspace):
        """Test that error message contains file content preview.

        When edit_file fails, the error message should:
        1. Show the expected text preview
        2. Show the current file content preview
        3. Provide a suggestion to use read_file
        """
        write_tool = WriteFileTool()
        edit_tool = EditFileTool()
        filepath = os.path.join(temp_dir, "test_error.txt")

        # Setup
        await write_tool.execute(path=filepath, content="Actual file content here\n")

        # Attempt edit with wrong old_text
        result = await edit_tool.execute(path=filepath, old_text="Wrong text", new_text="New text")

        # Verify error message structure
        assert "Error" in result, f"Should contain 'Error': {result}"
        assert "not found" in result.lower(), f"Should indicate text not found: {result}"
        assert "Current file content" in result or "content" in result.lower(), (
            f"Should show current content: {result}"
        )
        assert "Suggestion" in result or "suggestion" in result.lower(), (
            f"Should contain suggestion: {result}"
        )
        assert "read_file" in result.lower(), f"Should suggest read_file tool: {result}"

    @pytest.mark.asyncio
    async def test_error_message_shows_expected_text(self, temp_dir, mock_workspace):
        """Test that error message shows the expected text preview."""
        write_tool = WriteFileTool()
        edit_tool = EditFileTool()
        filepath = os.path.join(temp_dir, "test_expected.txt")

        await write_tool.execute(path=filepath, content="Current content\n")

        expected_text = "This is the text I expected to find"
        result = await edit_tool.execute(path=filepath, old_text=expected_text, new_text="New text")

        # The error should mention what was expected
        assert "Error" in result
        # Check that either the expected text or a preview is shown
        assert expected_text[:50] in result or "Expected text" in result, (
            f"Should show expected text: {result}"
        )

    @pytest.mark.asyncio
    async def test_error_message_truncates_long_content(self, temp_dir, mock_workspace):
        """Test that error message truncates very long content previews."""
        write_tool = WriteFileTool()
        edit_tool = EditFileTool()
        filepath = os.path.join(temp_dir, "test_long.txt")

        # Create file with very long content
        long_content = "Line " * 1000  # Very long content
        await write_tool.execute(path=filepath, content=long_content)

        result = await edit_tool.execute(path=filepath, old_text="Not found", new_text="New")

        assert "Error" in result
        # Error message should not be excessively long
        assert len(result) < 1000, f"Error message should be truncated: {len(result)} chars"

    # ========== Test 4: SuggestionEngine Recognizes Text Not Found ==========

    def test_suggestion_for_text_not_found(self):
        """Test SuggestionEngine recognizes text not found error."""
        engine = SuggestionEngine()

        # Test classification
        error_type = engine._classify_error("Error: Text not found in file")
        assert error_type == ErrorType.TEXT_NOT_FOUND, f"Expected TEXT_NOT_FOUND, got {error_type}"

        # Test suggestion content
        suggestion = engine.analyze_error("Error: Text not found in file")
        actions_str = str(suggestion.actions).lower()
        assert "read_file" in actions_str or "read" in actions_str, (
            f"Suggestion should mention read_file: {suggestion.actions}"
        )

    def test_suggestion_for_old_text_not_found(self):
        """Test SuggestionEngine recognizes old_text related errors."""
        engine = SuggestionEngine()

        error_type = engine._classify_error("old_text was not found in the file")
        assert error_type == ErrorType.TEXT_NOT_FOUND, (
            f"Expected TEXT_NOT_FOUND for old_text error, got {error_type}"
        )

    def test_suggestion_for_expected_text_not_found(self):
        """Test SuggestionEngine recognizes expected text errors."""
        engine = SuggestionEngine()

        error_type = engine._classify_error("Expected text not found during edit operation")
        assert error_type == ErrorType.TEXT_NOT_FOUND, f"Expected TEXT_NOT_FOUND, got {error_type}"

    def test_suggestion_text_not_found_has_priority(self):
        """Test that TEXT_NOT_FOUND suggestions have appropriate priority."""
        engine = SuggestionEngine()

        suggestions = engine.get_suggestions(ErrorType.TEXT_NOT_FOUND)

        assert len(suggestions) > 0, "Should have suggestions for TEXT_NOT_FOUND"
        # First suggestion should be high priority
        from mini_claude.agent.suggestion import Priority

        assert suggestions[0].priority == Priority.HIGH, (
            "TEXT_NOT_FOUND should have HIGH priority suggestion"
        )

    def test_suggestion_engine_chinese_text_not_found(self):
        """Test SuggestionEngine recognizes Chinese text not found errors."""
        engine = SuggestionEngine(language="zh")

        error_type = engine._classify_error("Error: 文本未找到")
        assert error_type == ErrorType.TEXT_NOT_FOUND, (
            f"Expected TEXT_NOT_FOUND for Chinese error, got {error_type}"
        )

        # Test Chinese suggestion content
        suggestion = engine.analyze_error("Error: 文本未找到")
        assert suggestion.title, "Should have a title"
        actions_str = str(suggestion.actions)
        # Chinese version should mention read_file or 读取
        assert "read_file" in actions_str.lower() or "读取" in actions_str, (
            f"Chinese suggestion should mention read_file: {suggestion.actions}"
        )

    def test_suggestion_engine_english_text_not_found(self):
        """Test SuggestionEngine with explicit English language."""
        engine = SuggestionEngine(language="en")

        error_type = engine._classify_error("Text not found in file")
        assert error_type == ErrorType.TEXT_NOT_FOUND

        suggestions = engine.get_suggestions(ErrorType.TEXT_NOT_FOUND)
        assert len(suggestions) > 0
        # English suggestion should mention read_file tool
        actions_str = str(suggestions[0].actions).lower()
        assert "read_file" in actions_str, (
            f"English suggestion should mention read_file: {suggestions[0].actions}"
        )


class TestEditFileRetryEdgeCases:
    """Test edge cases in edit_file retry scenarios."""

    @pytest.fixture
    def temp_dir(self):
        """Create a temporary directory for testing."""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield tmpdir

    @pytest.fixture
    def mock_workspace(self, temp_dir):
        """Mock the workspace root to the temp directory."""
        # Normalize path to resolve Windows 8.3 short names (RUNNER~1 -> runneradmin)
        normalized = str(Path(temp_dir).resolve())
        original_workspace = config_settings.workspace_root
        config_settings.workspace_root = normalized
        try:
            yield normalized
        finally:
            config_settings.workspace_root = original_workspace

    @pytest.mark.asyncio
    async def test_empty_file_edit_retry(self, temp_dir, mock_workspace):
        """Test retry scenario with empty file."""
        write_tool = WriteFileTool()
        edit_tool = EditFileTool()
        read_tool = ReadFileTool()
        filepath = os.path.join(temp_dir, "empty.txt")

        # Create empty file
        await write_tool.execute(path=filepath, content="")

        # Try to edit empty file - should fail
        result = await edit_tool.execute(path=filepath, old_text="something", new_text="new")
        assert "Error" in result or "not found" in result.lower()

        # Read file to confirm it's empty
        content = await read_tool.execute(path=filepath)
        assert content == ""

    @pytest.mark.asyncio
    async def test_unicode_content_retry(self, temp_dir, mock_workspace):
        """Test retry scenario with Unicode content."""
        write_tool = WriteFileTool()
        edit_tool = EditFileTool()
        read_tool = ReadFileTool()
        filepath = os.path.join(temp_dir, "unicode.txt")

        # Create file with Unicode content
        await write_tool.execute(path=filepath, content="中文内容\n日本語\n한국어\n")

        # First edit succeeds
        result1 = await edit_tool.execute(
            path=filepath, old_text="中文内容", new_text="修改后的内容"
        )
        assert "Successfully" in result1

        # Try with stale content - should fail
        result2 = await edit_tool.execute(path=filepath, old_text="中文内容", new_text="另一个修改")
        assert "Error" in result2

        # Read and retry
        current = await read_tool.execute(path=filepath)
        assert "修改后的内容" in current

        result3 = await edit_tool.execute(
            path=filepath, old_text="修改后的内容", new_text="另一个修改"
        )
        assert "Successfully" in result3

    @pytest.mark.asyncio
    async def test_multiline_content_retry(self, temp_dir, mock_workspace):
        """Test retry scenario with multiline content."""
        write_tool = WriteFileTool()
        edit_tool = EditFileTool()
        read_tool = ReadFileTool()
        filepath = os.path.join(temp_dir, "multiline.txt")

        content = """Line 1
Line 2
Line 3
Line 4
"""
        await write_tool.execute(path=filepath, content=content)

        # Edit multiline content
        result1 = await edit_tool.execute(
            path=filepath, old_text="Line 1\nLine 2", new_text="Modified Line 1"
        )
        assert "Successfully" in result1

        # Try with stale multiline content
        result2 = await edit_tool.execute(
            path=filepath, old_text="Line 1\nLine 2", new_text="Should fail"
        )
        assert "Error" in result2

        # Read and use correct content
        await read_tool.execute(path=filepath)
        result3 = await edit_tool.execute(
            path=filepath, old_text="Modified Line 1", new_text="Final content"
        )
        assert "Successfully" in result3

    @pytest.mark.asyncio
    async def test_similar_text_confusion(self, temp_dir, mock_workspace):
        """Test retry when user confuses similar text."""
        write_tool = WriteFileTool()
        edit_tool = EditFileTool()
        read_tool = ReadFileTool()
        filepath = os.path.join(temp_dir, "similar.txt")

        await write_tool.execute(path=filepath, content="function hello_world() {}\n")

        # Try with completely different text that is NOT a substring
        result1 = await edit_tool.execute(
            path=filepath, old_text="function goodbye_world() {}", new_text="def goodbye"
        )
        assert "Error" in result1 or "not found" in result1.lower(), (
            f"Should fail with non-existent text: {result1}"
        )

        # Read to see exact content
        await read_tool.execute(path=filepath)

        # Use exact text
        result2 = await edit_tool.execute(
            path=filepath, old_text="function hello_world() {}", new_text="def goodbye(): pass"
        )
        assert "Successfully" in result2


class TestEditFileRetryIntegration:
    """Integration tests combining edit_file retry with other tools."""

    @pytest.fixture
    def temp_dir(self):
        """Create a temporary directory for testing."""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield tmpdir

    @pytest.fixture
    def mock_workspace(self, temp_dir):
        """Mock the workspace root to the temp directory."""
        # Normalize path to resolve Windows 8.3 short names (RUNNER~1 -> runneradmin)
        normalized = str(Path(temp_dir).resolve())
        original_workspace = config_settings.workspace_root
        config_settings.workspace_root = normalized
        try:
            yield normalized
        finally:
            config_settings.workspace_root = original_workspace

    @pytest.mark.asyncio
    async def test_full_retry_workflow(self, temp_dir, mock_workspace):
        """Test the complete retry workflow from error to success.

        This simulates a real user workflow:
        1. Attempt edit with stale content -> fail
        2. Read file to get current content
        3. Retry edit with correct content -> succeed
        4. Verify final state
        """
        write_tool = WriteFileTool()
        edit_tool = EditFileTool()
        read_tool = ReadFileTool()
        filepath = os.path.join(temp_dir, "workflow.txt")

        # Initial content
        initial = "def hello():\n    print('Hello')\n"
        await write_tool.execute(path=filepath, content=initial)

        # Someone else modifies the file (or we forgot we modified it)
        await edit_tool.execute(
            path=filepath, old_text="print('Hello')", new_text="print('Goodbye')"
        )

        # We try to edit with stale content
        result = await edit_tool.execute(
            path=filepath, old_text="print('Hello')", new_text="print('World')"
        )
        assert "Error" in result, "Should fail with stale content"

        # Check error message quality
        assert "read_file" in result.lower(), "Should suggest read_file"
        assert "Content" in result or "content" in result.lower(), "Should show content preview"

        # Read current content
        current = await read_tool.execute(path=filepath)
        assert "print('Goodbye')" in current, "Should see current content"

        # Retry with correct content
        result2 = await edit_tool.execute(
            path=filepath, old_text="print('Goodbye')", new_text="print('World')"
        )
        assert "Successfully" in result2

        # Verify final state
        final = await read_tool.execute(path=filepath)
        assert "print('World')" in final
        assert "def hello():" in final  # Other content preserved
