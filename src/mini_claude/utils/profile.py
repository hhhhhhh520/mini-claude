"""User profile persistence for Mini Claude.

Stores user preferences, recent projects, and common workflows
in JSON format with concurrent access protection.
"""

import os
import json
import asyncio
from pathlib import Path
from datetime import datetime
from typing import Any, Dict, List, Optional
from dataclasses import dataclass, field, asdict

# File locking support
try:
    import fcntl

    HAS_FCNTL = True
except ImportError:
    HAS_FCNTL = False

try:
    import portalocker

    HAS_PORTALOCKER = True
except ImportError:
    HAS_PORTALOCKER = False


@dataclass
class UserProfile:
    """User profile data structure.

    Attributes:
        preferred_model: Default LLM model for interactions
        preferred_language: Language preference (e.g., 'zh-CN', 'en-US')
        recent_projects: List of recently accessed project paths
        common_workflows: List of frequently used workflow patterns
        custom_prompts: Custom prompt templates by name
        created_at: Profile creation timestamp
        updated_at: Last update timestamp
    """

    preferred_model: str = "deepseek-chat"
    preferred_language: str = "zh-CN"
    recent_projects: List[str] = field(default_factory=list)
    common_workflows: List[str] = field(default_factory=list)
    custom_prompts: Dict[str, str] = field(default_factory=dict)
    created_at: str = ""
    updated_at: str = ""

    def to_dict(self) -> Dict[str, Any]:
        """Convert profile to dictionary for JSON serialization."""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "UserProfile":
        """Create profile from dictionary."""
        return cls(
            preferred_model=data.get("preferred_model", "deepseek-chat"),
            preferred_language=data.get("preferred_language", "zh-CN"),
            recent_projects=data.get("recent_projects", []),
            common_workflows=data.get("common_workflows", []),
            custom_prompts=data.get("custom_prompts", {}),
            created_at=data.get("created_at", ""),
            updated_at=data.get("updated_at", ""),
        )


class UserProfileManager:
    """Manages user profile persistence with file locking.

    Features:
    - JSON format persistence to ~/.mini_claude/profile.json
    - Automatic directory creation
    - Concurrent access protection via file locking
    - Recent projects and workflows tracking
    """

    # Maximum items to keep in recent lists
    MAX_RECENT_PROJECTS = 10
    MAX_COMMON_WORKFLOWS = 20

    def __init__(self, profile_path: str = "~/.mini_claude/profile.json"):
        """Initialize profile manager.

        Args:
            profile_path: Path to profile JSON file (supports ~ expansion)
        """
        self._profile_path = str(Path(profile_path).expanduser())
        self._profile_dir = Path(self._profile_path).parent
        self._profile: Optional[UserProfile] = None
        self._lock = asyncio.Lock()

    def _ensure_dir(self) -> None:
        """Ensure profile directory exists."""
        self._profile_dir.mkdir(parents=True, exist_ok=True)

    def _acquire_file_lock(self, file_obj) -> bool:
        """Acquire exclusive file lock for concurrent access.

        Args:
            file_obj: Open file handle

        Returns:
            True if lock acquired, False otherwise
        """
        if HAS_PORTALOCKER:
            portalocker.lock(file_obj, portalocker.LOCK_EX)
            return True
        elif HAS_FCNTL:
            fcntl.flock(file_obj.fileno(), fcntl.LOCK_EX)
            return True
        else:
            # Windows without portalocker: use asyncio lock
            # Not ideal but provides basic protection
            return True

    def _release_file_lock(self, file_obj) -> None:
        """Release file lock."""
        if HAS_PORTALOCKER:
            portalocker.unlock(file_obj)
        elif HAS_FCNTL:
            fcntl.flock(file_obj.fileno(), fcntl.LOCK_UN)

    def load_profile(self) -> UserProfile:
        """Load user profile from JSON file.

        Creates default profile if file doesn't exist.

        Returns:
            UserProfile instance
        """

        # If profile already cached, return it
        if self._profile is not None:
            return self._profile

        # Check if file exists
        if not os.path.exists(self._profile_path):
            self._profile = UserProfile(
                created_at=datetime.now().isoformat(),
                updated_at=datetime.now().isoformat(),
            )
            return self._profile

        try:
            with open(self._profile_path, "r", encoding="utf-8") as f:
                self._acquire_file_lock(f)
                try:
                    data = json.load(f)
                    self._profile = UserProfile.from_dict(data)
                finally:
                    self._release_file_lock(f)
            return self._profile
        except (json.JSONDecodeError, IOError):
            # Return default profile on error
            self._profile = UserProfile(
                created_at=datetime.now().isoformat(),
                updated_at=datetime.now().isoformat(),
            )
            return self._profile

    def _sync_load(self) -> UserProfile:
        """Synchronous load for use within async lock."""
        if not os.path.exists(self._profile_path):
            return UserProfile(
                created_at=datetime.now().isoformat(),
                updated_at=datetime.now().isoformat(),
            )

        with open(self._profile_path, "r", encoding="utf-8") as f:
            self._acquire_file_lock(f)
            try:
                data = json.load(f)
                return UserProfile.from_dict(data)
            finally:
                self._release_file_lock(f)

    def save_profile(self, profile: UserProfile) -> bool:
        """Save user profile to JSON file.

        Args:
            profile: UserProfile instance to save

        Returns:
            True if saved successfully, False on error
        """

        self._ensure_dir()
        profile.updated_at = datetime.now().isoformat()

        try:
            with open(self._profile_path, "w", encoding="utf-8") as f:
                self._acquire_file_lock(f)
                try:
                    json.dump(profile.to_dict(), f, indent=2, ensure_ascii=False)
                finally:
                    self._release_file_lock(f)
            self._profile = profile
            return True
        except IOError:
            return False

    def _sync_save(self, profile: UserProfile) -> bool:
        """Synchronous save for use within async lock."""
        self._ensure_dir()
        profile.updated_at = datetime.now().isoformat()

        with open(self._profile_path, "w", encoding="utf-8") as f:
            self._acquire_file_lock(f)
            try:
                json.dump(profile.to_dict(), f, indent=2, ensure_ascii=False)
            finally:
                self._release_file_lock(f)
        self._profile = profile
        return True

    def update_preference(self, key: str, value: Any) -> bool:
        """Update a single preference in the profile.

        Args:
            key: Preference key (e.g., 'preferred_model', 'preferred_language')
            value: New value for the preference

        Returns:
            True if updated successfully, False on error
        """
        profile = self.load_profile()

        # Validate key is a valid profile field
        valid_keys = {
            "preferred_model",
            "preferred_language",
            "recent_projects",
            "common_workflows",
            "custom_prompts",
        }
        if key not in valid_keys:
            return False

        setattr(profile, key, value)
        return self.save_profile(profile)

    def get_preference(self, key: str, default: Any = None) -> Any:
        """Get a single preference from the profile.

        Args:
            key: Preference key
            default: Default value if key not found

        Returns:
            Preference value or default
        """
        profile = self.load_profile()

        if hasattr(profile, key):
            return getattr(profile, key)
        return default

    def add_recent_project(self, project_path: str) -> bool:
        """Add a project path to recent projects list.

        Maintains maximum list size by removing oldest entries.

        Args:
            project_path: Path to project directory

        Returns:
            True if added successfully
        """
        profile = self.load_profile()

        # Normalize path
        normalized_path = str(Path(project_path).resolve())

        # Remove if already exists (will be moved to front)
        if normalized_path in profile.recent_projects:
            profile.recent_projects.remove(normalized_path)

        # Add to front
        profile.recent_projects.insert(0, normalized_path)

        # Trim to max size
        if len(profile.recent_projects) > self.MAX_RECENT_PROJECTS:
            profile.recent_projects = profile.recent_projects[: self.MAX_RECENT_PROJECTS]

        return self.save_profile(profile)

    def add_common_workflow(self, workflow: str) -> bool:
        """Add a workflow pattern to common workflows list.

        Args:
            workflow: Workflow description or pattern

        Returns:
            True if added successfully
        """
        profile = self.load_profile()

        # Remove if already exists (will be moved to front)
        if workflow in profile.common_workflows:
            profile.common_workflows.remove(workflow)

        # Add to front
        profile.common_workflows.insert(0, workflow)

        # Trim to max size
        if len(profile.common_workflows) > self.MAX_COMMON_WORKFLOWS:
            profile.common_workflows = profile.common_workflows[: self.MAX_COMMON_WORKFLOWS]

        return self.save_profile(profile)

    def get_recent_projects(self, limit: int = 5) -> List[str]:
        """Get recent project paths.

        Args:
            limit: Maximum number to return

        Returns:
            List of project paths
        """
        profile = self.load_profile()
        return profile.recent_projects[:limit]

    def get_common_workflows(self, limit: int = 10) -> List[str]:
        """Get common workflow patterns.

        Args:
            limit: Maximum number to return

        Returns:
            List of workflows
        """
        profile = self.load_profile()
        return profile.common_workflows[:limit]

    def add_custom_prompt(self, name: str, prompt: str) -> bool:
        """Add or update a custom prompt template.

        Args:
            name: Prompt name/identifier
            prompt: Prompt template content

        Returns:
            True if added successfully
        """
        profile = self.load_profile()
        profile.custom_prompts[name] = prompt
        return self.save_profile(profile)

    def get_custom_prompt(self, name: str) -> Optional[str]:
        """Get a custom prompt template.

        Args:
            name: Prompt name

        Returns:
            Prompt content or None if not found
        """
        profile = self.load_profile()
        return profile.custom_prompts.get(name)

    def remove_custom_prompt(self, name: str) -> bool:
        """Remove a custom prompt template.

        Args:
            name: Prompt name

        Returns:
            True if removed, False if not found
        """
        profile = self.load_profile()

        if name not in profile.custom_prompts:
            return False

        del profile.custom_prompts[name]
        return self.save_profile(profile)

    def clear_profile(self) -> bool:
        """Clear all profile data and reset to defaults.

        Returns:
            True if cleared successfully
        """
        self._profile = UserProfile(
            created_at=datetime.now().isoformat(),
            updated_at=datetime.now().isoformat(),
        )
        return self.save_profile(self._profile)

    def get_profile_path(self) -> str:
        """Get the profile file path."""
        return self._profile_path
