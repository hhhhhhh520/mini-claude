"""Tests for settings.py configuration."""

import pytest
from pathlib import Path

from mini_claude.config.settings import Settings, VectorDBType


class TestVectorDBSettings:
    """Tests for vector database configuration."""

    def test_default_vector_db_type(self):
        """Test default vector_db_type is chroma."""
        settings = Settings()
        assert settings.vector_db_type == "chroma"

    def test_default_vector_db_path_expanded(self):
        """Test vector_db_path expands ~ to home directory."""
        settings = Settings()
        expected = str(Path("~/.mini_claude/vectors").expanduser())
        assert settings.vector_db_path == expected
        assert "~" not in settings.vector_db_path  # Should be expanded

    def test_default_embedding_model(self):
        """Test default embedding model."""
        settings = Settings()
        assert settings.embedding_model == "sentence-transformers/all-MiniLM-L6-v2"

    def test_default_semantic_search_enabled(self):
        """Test semantic search is enabled by default."""
        settings = Settings()
        assert settings.enable_semantic_search is True

    def test_valid_vector_db_type_chroma(self):
        """Test chroma is a valid vector_db_type."""
        settings = Settings(vector_db_type="chroma")
        assert settings.vector_db_type == "chroma"

    def test_valid_vector_db_type_faiss(self):
        """Test faiss is a valid vector_db_type."""
        settings = Settings(vector_db_type="faiss")
        assert settings.vector_db_type == "faiss"

    def test_vector_db_type_case_insensitive(self):
        """Test vector_db_type validation is case insensitive."""
        settings = Settings(vector_db_type="CHROMA")
        assert settings.vector_db_type == "chroma"

        settings2 = Settings(vector_db_type="Faiss")
        assert settings2.vector_db_type == "faiss"

    def test_invalid_vector_db_type_raises_error(self):
        """Test invalid vector_db_type raises ValueError."""
        with pytest.raises(ValueError) as exc_info:
            Settings(vector_db_type="invalid_db")
        assert "vector_db_type must be one of" in str(exc_info.value)

    def test_custom_vector_db_path(self):
        """Test custom vector_db_path."""
        custom_path = "/custom/path/to/vectors"
        settings = Settings(vector_db_path=custom_path)
        # Path normalizes separators based on OS
        assert settings.vector_db_path == str(Path(custom_path))


class TestUserProfileSettings:
    """Tests for user profile configuration."""

    def test_default_user_profile_path_expanded(self):
        """Test user_profile_path expands ~ to home directory."""
        settings = Settings()
        expected = str(Path("~/.mini_claude/profile.json").expanduser())
        assert settings.user_profile_path == expected
        assert "~" not in settings.user_profile_path

    def test_default_profile_auto_save(self):
        """Test auto save is enabled by default."""
        settings = Settings()
        assert settings.profile_auto_save is True

    def test_default_profile_save_interval(self):
        """Test default save interval is 300 seconds."""
        settings = Settings()
        assert settings.profile_save_interval == 300

    def test_custom_profile_save_interval(self):
        """Test custom save interval."""
        settings = Settings(profile_save_interval=600)
        assert settings.profile_save_interval == 600

    def test_zero_save_interval_allowed(self):
        """Test zero save interval is allowed (disabled)."""
        settings = Settings(profile_save_interval=0)
        assert settings.profile_save_interval == 0

    def test_negative_save_interval_raises_error(self):
        """Test negative save interval raises ValueError."""
        with pytest.raises(ValueError) as exc_info:
            Settings(profile_save_interval=-1)
        assert "profile_save_interval must be non-negative" in str(exc_info.value)

    def test_custom_user_profile_path(self):
        """Test custom user_profile_path."""
        custom_path = "/custom/path/to/profile.json"
        settings = Settings(user_profile_path=custom_path)
        # Path normalizes separators based on OS
        assert settings.user_profile_path == str(Path(custom_path))


class TestSettingsBackwardCompatibility:
    """Tests for backward compatibility with existing settings."""

    def test_existing_settings_unchanged(self):
        """Test existing settings remain unchanged."""
        settings = Settings()
        # Check existing settings still have default values
        # Note: default_model changed from "deepseek-chat" to "deepseek-v4-flash"
        assert settings.default_model == "deepseek-v4-flash"
        assert settings.max_sub_agents == 3
        assert settings.max_iterations == 10
        assert settings.streaming_enabled is True
        assert settings.log_level == "INFO"

    def test_new_settings_dont_affect_existing(self):
        """Test new settings don't break existing functionality."""
        settings = Settings(default_model="gpt-4", max_iterations=20, vector_db_type="faiss")
        assert settings.default_model == "gpt-4"
        assert settings.max_iterations == 20
        assert settings.vector_db_type == "faiss"


class TestVectorDBTypeEnum:
    """Tests for VectorDBType enum."""

    def test_enum_values(self):
        """Test VectorDBType enum has correct values."""
        assert VectorDBType.CHROMA.value == "chroma"
        assert VectorDBType.FAISS.value == "faiss"

    def test_enum_count(self):
        """Test VectorDBType has exactly 2 values."""
        assert len(VectorDBType) == 2


class TestPathExpansion:
    """Tests for path expansion functionality."""

    def test_home_directory_expansion_vector_db(self):
        """Test home directory expansion for vector_db_path."""
        settings = Settings(vector_db_path="~/custom/vectors")
        assert settings.vector_db_path.startswith(str(Path.home()))
        assert "~" not in settings.vector_db_path

    def test_home_directory_expansion_user_profile(self):
        """Test home directory expansion for user_profile_path."""
        settings = Settings(user_profile_path="~/custom/profile.json")
        assert settings.user_profile_path.startswith(str(Path.home()))
        assert "~" not in settings.user_profile_path

    def test_absolute_path_unchanged(self):
        """Test absolute paths remain unchanged (except separator normalization)."""
        abs_path = "/absolute/path/to/vectors"
        settings = Settings(vector_db_path=abs_path)
        # Path normalizes separators based on OS, but content remains
        assert settings.vector_db_path == str(Path(abs_path))

    def test_relative_path_unchanged(self):
        """Test relative paths remain unchanged (not expanded, separator normalized)."""
        rel_path = "relative/path/to/vectors"
        settings = Settings(vector_db_path=rel_path)
        # Relative paths should remain as-is (validator only expands ~)
        # Path normalizes separators based on OS
        assert settings.vector_db_path == str(Path(rel_path))
