"""Tests for user profile persistence."""

import pytest
import os
import json
import tempfile
from pathlib import Path
from unittest.mock import patch

from mini_claude.utils.profile import UserProfile, UserProfileManager


@pytest.fixture
def temp_profile_path():
    """Create a temporary profile path for testing."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield os.path.join(tmpdir, "profile.json")


@pytest.fixture
def profile_manager(temp_profile_path):
    """Create a UserProfileManager with temporary path."""
    return UserProfileManager(profile_path=temp_profile_path)


# ========== UserProfile Dataclass Tests ==========

class TestUserProfile:
    """Tests for UserProfile dataclass - 8 test cases."""

    def test_default_values(self):
        """Test default profile values."""
        profile = UserProfile()
        assert profile.preferred_model == "deepseek-chat"
        assert profile.preferred_language == "zh-CN"
        assert profile.recent_projects == []
        assert profile.common_workflows == []
        assert profile.custom_prompts == {}

    def test_custom_values(self):
        """Test custom profile values."""
        profile = UserProfile(
            preferred_model="gpt-4",
            preferred_language="en-US",
            recent_projects=["/path/to/project"],
        )
        assert profile.preferred_model == "gpt-4"
        assert profile.preferred_language == "en-US"
        assert profile.recent_projects == ["/path/to/project"]

    def test_to_dict(self):
        """Test conversion to dictionary."""
        profile = UserProfile(
            preferred_model="claude-3",
            preferred_language="en-US",
            recent_projects=["/project1", "/project2"],
        )
        data = profile.to_dict()

        assert data["preferred_model"] == "claude-3"
        assert data["preferred_language"] == "en-US"
        assert data["recent_projects"] == ["/project1", "/project2"]
        assert "created_at" in data
        assert "updated_at" in data

    def test_from_dict(self):
        """Test creation from dictionary."""
        data = {
            "preferred_model": "gemini-pro",
            "preferred_language": "ja-JP",
            "recent_projects": ["/project"],
            "custom_prompts": {"test": "prompt"},
        }
        profile = UserProfile.from_dict(data)

        assert profile.preferred_model == "gemini-pro"
        assert profile.preferred_language == "ja-JP"
        assert profile.recent_projects == ["/project"]
        assert profile.custom_prompts == {"test": "prompt"}

    def test_from_dict_missing_fields(self):
        """Test creation from dictionary with missing fields."""
        data = {}
        profile = UserProfile.from_dict(data)

        # Should use defaults
        assert profile.preferred_model == "deepseek-chat"
        assert profile.preferred_language == "zh-CN"

    def test_timestamps(self):
        """Test timestamp handling."""
        profile = UserProfile(
            created_at="2024-01-01T00:00:00",
            updated_at="2024-01-02T00:00:00",
        )
        assert profile.created_at == "2024-01-01T00:00:00"
        assert profile.updated_at == "2024-01-02T00:00:00"

    def test_custom_prompts_operations(self):
        """Test custom prompts dictionary operations."""
        profile = UserProfile()
        profile.custom_prompts["review"] = "Review this code"
        profile.custom_prompts["test"] = "Write tests"

        assert len(profile.custom_prompts) == 2
        assert profile.custom_prompts["review"] == "Review this code"

    def test_serialization_roundtrip(self):
        """Test serialization and deserialization roundtrip."""
        original = UserProfile(
            preferred_model="claude-3-opus",
            preferred_language="zh-CN",
            recent_projects=["/p1", "/p2"],
            common_workflows=["code review", "testing"],
            custom_prompts={"key": "value"},
        )

        data = original.to_dict()
        restored = UserProfile.from_dict(data)

        assert restored.preferred_model == original.preferred_model
        assert restored.preferred_language == original.preferred_language
        assert restored.recent_projects == original.recent_projects
        assert restored.common_workflows == original.common_workflows
        assert restored.custom_prompts == original.custom_prompts


# ========== UserProfileManager Tests ==========

class TestUserProfileManager:
    """Tests for UserProfileManager - 20 test cases."""

    def test_init_with_expanded_path(self, temp_profile_path):
        """Test path expansion in constructor."""
        manager = UserProfileManager(profile_path="~/test/profile.json")
        assert "~" not in manager._profile_path
        assert manager._profile_path.startswith(str(Path.home()))

    def test_load_profile_creates_default(self, profile_manager):
        """Test loading non-existent profile creates default."""
        profile = profile_manager.load_profile()

        assert profile.preferred_model == "deepseek-chat"
        assert profile.preferred_language == "zh-CN"
        assert len(profile.recent_projects) == 0

    def test_save_and_load_profile(self, profile_manager):
        """Test saving and loading profile."""
        profile = UserProfile(
            preferred_model="gpt-4",
            preferred_language="en-US",
        )
        assert profile_manager.save_profile(profile) is True

        loaded = profile_manager.load_profile()
        assert loaded.preferred_model == "gpt-4"
        assert loaded.preferred_language == "en-US"

    def test_update_preference(self, profile_manager):
        """Test updating a single preference."""
        profile_manager.load_profile()
        result = profile_manager.update_preference("preferred_model", "claude-3")

        assert result is True
        assert profile_manager.get_preference("preferred_model") == "claude-3"

    def test_update_invalid_preference(self, profile_manager):
        """Test updating invalid preference key."""
        profile_manager.load_profile()
        result = profile_manager.update_preference("invalid_key", "value")

        assert result is False

    def test_get_preference_with_default(self, profile_manager):
        """Test getting preference with default value."""
        value = profile_manager.get_preference("nonexistent", "default_value")
        assert value == "default_value"

    def test_add_recent_project(self, profile_manager):
        """Test adding recent project."""
        profile_manager.load_profile()
        result = profile_manager.add_recent_project("/path/to/project")

        assert result is True
        projects = profile_manager.get_recent_projects()
        # Path is normalized, check if project path is in the result
        assert any("project" in p for p in projects)

    def test_add_recent_project_moves_to_front(self, profile_manager):
        """Test adding existing project moves it to front."""
        profile_manager.load_profile()
        profile_manager.add_recent_project("/project1")
        profile_manager.add_recent_project("/project2")
        profile_manager.add_recent_project("/project1")

        projects = profile_manager.get_recent_projects()
        assert projects[0].endswith("project1") or "project1" in projects[0]

    def test_max_recent_projects_limit(self, profile_manager):
        """Test recent projects limit."""
        profile_manager.load_profile()

        # Add more than limit
        for i in range(15):
            profile_manager.add_recent_project(f"/project{i}")

        projects = profile_manager.get_recent_projects(limit=20)
        assert len(projects) == UserProfileManager.MAX_RECENT_PROJECTS

    def test_add_common_workflow(self, profile_manager):
        """Test adding common workflow."""
        profile_manager.load_profile()
        result = profile_manager.add_common_workflow("code review")

        assert result is True
        workflows = profile_manager.get_common_workflows()
        assert "code review" in workflows

    def test_get_recent_projects_limit(self, profile_manager):
        """Test get_recent_projects respects limit."""
        profile_manager.load_profile()
        for i in range(10):
            profile_manager.add_recent_project(f"/project{i}")

        projects = profile_manager.get_recent_projects(limit=3)
        assert len(projects) == 3

    def test_get_common_workflows_limit(self, profile_manager):
        """Test get_common_workflows respects limit."""
        profile_manager.load_profile()
        for i in range(15):
            profile_manager.add_common_workflow(f"workflow{i}")

        workflows = profile_manager.get_common_workflows(limit=5)
        assert len(workflows) == 5

    def test_custom_prompt_operations(self, profile_manager):
        """Test custom prompt add, get, remove."""
        profile_manager.load_profile()

        # Add
        result = profile_manager.add_custom_prompt("review", "Review this code")
        assert result is True

        # Get
        prompt = profile_manager.get_custom_prompt("review")
        assert prompt == "Review this code"

        # Remove
        result = profile_manager.remove_custom_prompt("review")
        assert result is True

        # Verify removed
        prompt = profile_manager.get_custom_prompt("review")
        assert prompt is None

    def test_remove_nonexistent_prompt(self, profile_manager):
        """Test removing nonexistent prompt."""
        profile_manager.load_profile()
        result = profile_manager.remove_custom_prompt("nonexistent")
        assert result is False

    def test_clear_profile(self, profile_manager):
        """Test clearing profile."""
        profile_manager.load_profile()
        profile_manager.update_preference("preferred_model", "gpt-4")
        profile_manager.add_recent_project("/project")

        result = profile_manager.clear_profile()
        assert result is True

        profile = profile_manager.load_profile()
        assert profile.preferred_model == "deepseek-chat"
        assert len(profile.recent_projects) == 0

    def test_get_profile_path(self, profile_manager, temp_profile_path):
        """Test getting profile path."""
        path = profile_manager.get_profile_path()
        assert path == str(Path(temp_profile_path).expanduser())

    def test_profile_file_format(self, profile_manager):
        """Test profile file is valid JSON."""
        profile_manager.load_profile()
        profile_manager.update_preference("preferred_model", "test-model")

        # Read file directly
        with open(profile_manager._profile_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        assert data["preferred_model"] == "test-model"

    def test_profile_directory_auto_creation(self):
        """Test profile directory is created automatically."""
        with tempfile.TemporaryDirectory() as tmpdir:
            profile_path = os.path.join(tmpdir, "nested", "dir", "profile.json")
            manager = UserProfileManager(profile_path=profile_path)
            profile = manager.load_profile()
            # Save triggers directory creation
            manager.save_profile(profile)

            assert os.path.exists(os.path.dirname(manager._profile_path))

    def test_load_corrupted_json(self, temp_profile_path):
        """Test loading corrupted JSON file returns default."""
        # Write invalid JSON
        os.makedirs(os.path.dirname(temp_profile_path), exist_ok=True)
        with open(temp_profile_path, "w") as f:
            f.write("{ invalid json }")

        manager = UserProfileManager(profile_path=temp_profile_path)
        profile = manager.load_profile()

        # Should return default profile
        assert profile.preferred_model == "deepseek-chat"

    def test_unicode_path_support(self):
        """Test Unicode path in recent projects."""
        with tempfile.TemporaryDirectory() as tmpdir:
            profile_path = os.path.join(tmpdir, "profile.json")
            manager = UserProfileManager(profile_path=profile_path)
            manager.load_profile()

            unicode_path = os.path.join(tmpdir, "Chinese")
            manager.add_recent_project(unicode_path)

            projects = manager.get_recent_projects()
            assert len(projects) == 1


# ========== Concurrent Access Tests ==========

class TestConcurrentAccess:
    """Tests for concurrent access protection - 5 test cases."""

    def test_manager_with_same_path(self):
        """Test multiple managers with same path."""
        with tempfile.TemporaryDirectory() as tmpdir:
            profile_path = os.path.join(tmpdir, "profile.json")

            manager1 = UserProfileManager(profile_path=profile_path)
            manager2 = UserProfileManager(profile_path=profile_path)

            manager1.load_profile()
            manager1.update_preference("preferred_model", "model1")

            # Manager2 should see the change
            assert manager2.get_preference("preferred_model") == "model1"

    def test_profile_caching(self, profile_manager):
        """Test profile is cached after first load."""
        profile_manager.load_profile()

        # Second load should return cached profile
        profile1 = profile_manager.load_profile()
        profile2 = profile_manager.load_profile()

        assert profile1 is profile2

    def test_save_updates_cache(self, profile_manager):
        """Test saving updates cached profile."""
        profile = UserProfile(preferred_model="new-model")
        profile_manager.save_profile(profile)

        # Should return cached version
        loaded = profile_manager.load_profile()
        assert loaded.preferred_model == "new-model"

    def test_file_persistence_across_managers(self):
        """Test profile persists across manager instances."""
        with tempfile.TemporaryDirectory() as tmpdir:
            profile_path = os.path.join(tmpdir, "profile.json")

            # Create and save with first manager
            manager1 = UserProfileManager(profile_path=profile_path)
            manager1.load_profile()
            manager1.update_preference("preferred_model", "persistent-model")

            # Create new manager and load
            manager2 = UserProfileManager(profile_path=profile_path)
            assert manager2.get_preference("preferred_model") == "persistent-model"

    def test_empty_profile_file(self, temp_profile_path):
        """Test loading empty profile file."""
        os.makedirs(os.path.dirname(temp_profile_path), exist_ok=True)
        with open(temp_profile_path, "w") as f:
            f.write("")

        manager = UserProfileManager(profile_path=temp_profile_path)
        profile = manager.load_profile()

        # Should return default profile
        assert profile.preferred_model == "deepseek-chat"
