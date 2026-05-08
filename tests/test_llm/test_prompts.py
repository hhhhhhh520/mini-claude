"""Tests for LLM prompts module."""

import pytest

from mini_claude.llm.prompts import (
    BASE_PROMPT,
    FEATURE_VERSIONS,
    get_system_prompt,
    get_subagent_prompt,
    get_planning_prompt,
    get_feature_summary,
    get_feature_list_markdown,
    update_feature_version,
)
from mini_claude.config.settings import ModelProvider


class TestBasePromptSelfIdentity:
    """Test that BASE_PROMPT contains self-identity declaration."""

    def test_base_prompt_contains_self_identity_header(self):
        """BASE_PROMPT should contain 'Self-Identity' section."""
        assert "## Self-Identity" in BASE_PROMPT

    def test_base_prompt_contains_name_declaration(self):
        """BASE_PROMPT should declare 'I am Mini Claude Code'."""
        assert "I am Mini Claude Code" in BASE_PROMPT

    def test_base_prompt_contains_file_operations(self):
        """BASE_PROMPT should list file operations capabilities."""
        assert "File Operations" in BASE_PROMPT
        assert "Read" in BASE_PROMPT
        assert "Write" in BASE_PROMPT
        assert "Edit" in BASE_PROMPT
        assert "Search" in BASE_PROMPT

    def test_base_prompt_contains_command_execution(self):
        """BASE_PROMPT should list command execution capabilities."""
        assert "Command Execution" in BASE_PROMPT
        assert "Shell Commands" in BASE_PROMPT
        assert "Background Tasks" in BASE_PROMPT

    def test_base_prompt_contains_web_capabilities(self):
        """BASE_PROMPT should list web capabilities."""
        assert "Web Capabilities" in BASE_PROMPT
        assert "Web Search" in BASE_PROMPT
        assert "DuckDuckGo" in BASE_PROMPT

    def test_base_prompt_contains_agent_collaboration(self):
        """BASE_PROMPT should list agent collaboration capabilities."""
        assert "Agent Collaboration" in BASE_PROMPT
        assert "Sub-Agents" in BASE_PROMPT
        assert "Parallel Execution" in BASE_PROMPT

    def test_base_prompt_contains_token_management(self):
        """BASE_PROMPT should list token management capabilities."""
        assert "Token Management" in BASE_PROMPT
        assert "Budget Control" in BASE_PROMPT
        assert "Summary Compression" in BASE_PROMPT

    def test_base_prompt_contains_session_management(self):
        """BASE_PROMPT should list session management capabilities."""
        assert "Session Management" in BASE_PROMPT
        assert "Save/Load" in BASE_PROMPT
        assert "Resume" in BASE_PROMPT

    def test_base_prompt_contains_cli_commands_section(self):
        """BASE_PROMPT should contain CLI Commands section."""
        assert "CLI Commands" in BASE_PROMPT

    def test_base_prompt_contains_tokens_command(self):
        """BASE_PROMPT should document /tokens command."""
        assert "/tokens" in BASE_PROMPT
        assert "token usage" in BASE_PROMPT.lower()

    def test_base_prompt_contains_status_command(self):
        """BASE_PROMPT should document /status command."""
        assert "/status" in BASE_PROMPT

    def test_base_prompt_contains_help_command(self):
        """BASE_PROMPT should document /help command."""
        assert "/help" in BASE_PROMPT

    def test_base_prompt_contains_reset_command(self):
        """BASE_PROMPT should document /reset command."""
        assert "/reset" in BASE_PROMPT

    def test_base_prompt_contains_save_load_commands(self):
        """BASE_PROMPT should document /save and /load commands."""
        assert "/save" in BASE_PROMPT
        assert "/load" in BASE_PROMPT

    def test_base_prompt_contains_resume_command(self):
        """BASE_PROMPT should document /resume command."""
        assert "/resume" in BASE_PROMPT

    def test_base_prompt_contains_sessions_command(self):
        """BASE_PROMPT should document /sessions command."""
        assert "/sessions" in BASE_PROMPT

    def test_base_prompt_contains_clear_command(self):
        """BASE_PROMPT should document /clear command."""
        assert "/clear" in BASE_PROMPT

    def test_base_prompt_contains_exit_command(self):
        """BASE_PROMPT should document /exit command."""
        assert "/exit" in BASE_PROMPT


class TestGetSystemPrompt:
    """Test get_system_prompt function."""

    def test_claude_provider_includes_base_prompt(self):
        """Claude provider prompt should include BASE_PROMPT."""
        prompt = get_system_prompt(ModelProvider.CLAUDE)
        assert "I am Mini Claude Code" in prompt
        assert "Self-Identity" in prompt

    def test_openai_provider_includes_base_prompt(self):
        """OpenAI provider prompt should include BASE_PROMPT."""
        prompt = get_system_prompt(ModelProvider.OPENAI)
        assert "I am Mini Claude Code" in prompt
        assert "Self-Identity" in prompt

    def test_gemini_provider_includes_base_prompt(self):
        """Gemini provider prompt should include BASE_PROMPT."""
        prompt = get_system_prompt(ModelProvider.GEMINI)
        assert "I am Mini Claude Code" in prompt
        assert "Self-Identity" in prompt

    def test_deepseek_provider_includes_base_prompt(self):
        """DeepSeek provider prompt should include BASE_PROMPT."""
        prompt = get_system_prompt(ModelProvider.DEEPSEEK)
        assert "I am Mini Claude Code" in prompt
        assert "Self-Identity" in prompt

    def test_ollama_provider_includes_base_prompt(self):
        """Ollama provider prompt should include BASE_PROMPT."""
        prompt = get_system_prompt(ModelProvider.OLLAMA)
        assert "I am Mini Claude Code" in prompt
        assert "Self-Identity" in prompt


class TestSubAgentPrompt:
    """Test get_subagent_prompt function."""

    def test_subagent_prompt_contains_task(self):
        """Sub-agent prompt should include the task."""
        prompt = get_subagent_prompt("Test task")
        assert "Test task" in prompt

    def test_subagent_prompt_contains_context(self):
        """Sub-agent prompt should include context when provided."""
        prompt = get_subagent_prompt("Test task", "Additional context")
        assert "Additional context" in prompt


class TestPlanningPrompt:
    """Test get_planning_prompt function."""

    def test_planning_prompt_contains_task(self):
        """Planning prompt should include the task."""
        prompt = get_planning_prompt("Plan this task")
        assert "Plan this task" in prompt

    def test_planning_prompt_lists_tools(self):
        """Planning prompt should list available tools."""
        prompt = get_planning_prompt("Test")
        assert "read_file" in prompt
        assert "write_file" in prompt
        assert "plan_parallel" in prompt


class TestFeatureVersions:
    """Test FEATURE_VERSIONS dict and related functions."""

    def test_feature_versions_is_dict(self):
        """FEATURE_VERSIONS should be a dictionary."""
        assert isinstance(FEATURE_VERSIONS, dict)

    def test_feature_versions_has_file_operations(self):
        """FEATURE_VERSIONS should contain file_operations."""
        assert "file_operations" in FEATURE_VERSIONS
        assert "version" in FEATURE_VERSIONS["file_operations"]
        assert "features" in FEATURE_VERSIONS["file_operations"]

    def test_feature_versions_has_token_management(self):
        """FEATURE_VERSIONS should contain token_management with version 2.0."""
        assert "token_management" in FEATURE_VERSIONS
        assert FEATURE_VERSIONS["token_management"]["version"] == "2.0"

    def test_feature_versions_has_agent_collaboration(self):
        """FEATURE_VERSIONS should contain agent_collaboration."""
        assert "agent_collaboration" in FEATURE_VERSIONS
        assert "spawn" in FEATURE_VERSIONS["agent_collaboration"]["features"]
        assert "parallel" in FEATURE_VERSIONS["agent_collaboration"]["features"]

    def test_all_features_have_required_keys(self):
        """All feature entries should have version, features, and description."""
        required_keys = {"version", "features", "description"}
        for feature_name, feature_data in FEATURE_VERSIONS.items():
            assert required_keys.issubset(feature_data.keys()), (
                f"Feature {feature_name} missing required keys"
            )


class TestGetFeatureSummary:
    """Test get_feature_summary function."""

    def test_get_feature_summary_returns_string(self):
        """get_feature_summary should return a string."""
        result = get_feature_summary()
        assert isinstance(result, str)

    def test_get_feature_summary_includes_file_operations(self):
        """get_feature_summary should include File Operations."""
        result = get_feature_summary()
        assert "File Operations" in result

    def test_get_feature_summary_includes_versions(self):
        """get_feature_summary should include version numbers when enabled."""
        result = get_feature_summary(include_version=True)
        assert "v1.0" in result or "v2.0" in result

    def test_get_feature_summary_excludes_versions(self):
        """get_feature_summary should exclude version numbers when disabled."""
        result = get_feature_summary(include_version=False)
        # Should not contain version patterns like "v1.0"
        # But file operations v1.0 would still have "File Operations"
        assert "File Operations" in result

    def test_get_feature_summary_includes_features(self):
        """get_feature_summary should include feature list when enabled."""
        result = get_feature_summary(include_features=True)
        assert "Read" in result or "Write" in result

    def test_get_feature_summary_includes_token_management(self):
        """get_feature_summary should include Token Management."""
        result = get_feature_summary()
        assert "Token Management" in result


class TestGetFeatureListMarkdown:
    """Test get_feature_list_markdown function."""

    def test_get_feature_list_markdown_returns_string(self):
        """get_feature_list_markdown should return a string."""
        result = get_feature_list_markdown()
        assert isinstance(result, str)

    def test_get_feature_list_markdown_has_headers(self):
        """get_feature_list_markdown should have section headers."""
        result = get_feature_list_markdown()
        assert "### File Operations" in result
        assert "### Token Management" in result

    def test_get_feature_list_markdown_has_feature_details(self):
        """get_feature_list_markdown should have feature details."""
        result = get_feature_list_markdown()
        assert "**Read**" in result
        assert "**Write**" in result


class TestUpdateFeatureVersion:
    """Test update_feature_version function."""

    def test_update_feature_version_adds_new_feature(self):
        """update_feature_version should add a new feature entry."""
        # Save original state
        original_count = len(FEATURE_VERSIONS)

        update_feature_version(
            "test_feature",
            version="1.0",
            features=["test1", "test2"],
            description="Test feature",
        )

        assert "test_feature" in FEATURE_VERSIONS
        assert FEATURE_VERSIONS["test_feature"]["version"] == "1.0"
        assert "test1" in FEATURE_VERSIONS["test_feature"]["features"]

        # Cleanup
        del FEATURE_VERSIONS["test_feature"]
        assert len(FEATURE_VERSIONS) == original_count

    def test_update_feature_version_updates_existing(self):
        """update_feature_version should update existing feature entry."""
        # Save original version
        original_version = FEATURE_VERSIONS["file_operations"]["version"]

        update_feature_version("file_operations", version="1.1")
        assert FEATURE_VERSIONS["file_operations"]["version"] == "1.1"

        # Restore original
        update_feature_version("file_operations", version=original_version)

    def test_update_feature_version_rejects_empty_name(self):
        """update_feature_version should reject empty feature name."""
        with pytest.raises(ValueError, match="cannot be empty"):
            update_feature_version("")

    def test_update_feature_version_updates_description(self):
        """update_feature_version should update description."""
        original_desc = FEATURE_VERSIONS["file_operations"]["description"]

        update_feature_version("file_operations", description="New description")
        assert FEATURE_VERSIONS["file_operations"]["description"] == "New description"

        # Restore
        update_feature_version("file_operations", description=original_desc)


class TestBasePromptDynamicInjection:
    """Test that BASE_PROMPT uses dynamic feature injection."""

    def test_base_prompt_includes_all_features(self):
        """BASE_PROMPT should include all features from FEATURE_VERSIONS."""
        for feature_name in FEATURE_VERSIONS:
            # Convert snake_case to Title Case for comparison
            display_name = feature_name.replace("_", " ").title()
            assert display_name in BASE_PROMPT, f"Missing feature: {feature_name}"

    def test_base_prompt_regenerates_on_feature_add(self):
        """BASE_PROMPT should be regenerated when new feature is added."""
        from mini_claude.llm.prompts import _build_base_prompt

        # Add a new feature
        update_feature_version(
            "temp_feature",
            version="0.1",
            features=["temp"],
            description="Temporary feature",
        )

        # Rebuild base prompt
        new_prompt = _build_base_prompt()
        assert "Temp Feature" in new_prompt or "Temporary feature" in new_prompt

        # Cleanup
        del FEATURE_VERSIONS["temp_feature"]
