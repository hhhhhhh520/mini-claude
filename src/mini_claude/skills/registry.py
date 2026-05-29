"""Skill registry — singleton that manages all loaded skills."""

import logging
from pathlib import Path
from typing import Dict, List, Optional

from .loader import discover_skills
from .models import Skill

logger = logging.getLogger(__name__)


class SkillRegistry:
    """Registry for loaded skills.

    Provides lookup by name, listing, and prompt generation for system prompt injection.
    """

    def __init__(self):
        self._skills: Dict[str, Skill] = {}
        self._loaded = False

    def load(
        self,
        user_skills_dir: Optional[Path] = None,
        project_skills_dir: Optional[Path] = None,
    ) -> int:
        """Load skills from configured directories.

        Args:
            user_skills_dir: User-level skills directory
            project_skills_dir: Project-level skills directory

        Returns:
            Number of skills loaded
        """
        self._skills.clear()
        skills = discover_skills(user_skills_dir, project_skills_dir)
        for skill in skills:
            self._skills[skill.name] = skill
        self._loaded = True
        logger.info("Loaded %d skills", len(self._skills))
        return len(self._skills)

    def get(self, name: str) -> Optional[Skill]:
        """Look up a skill by name.

        Args:
            name: Skill name (case-insensitive)

        Returns:
            Skill if found, None otherwise
        """
        return self._skills.get(name.lower()) or self._skills.get(name)

    def list_skills(self) -> List[Skill]:
        """Return all loaded skills."""
        return list(self._skills.values())

    def is_loaded(self) -> bool:
        """Check if registry has been loaded."""
        return self._loaded

    def get_skill_prompt(self) -> str:
        """Generate a markdown block listing all skills for system prompt injection.

        Includes skill descriptions AND full body content so the LLM
        can directly follow skill instructions without needing to invoke them.

        Returns:
            Formatted string with skill names, descriptions, and bodies, or empty string if no skills
        """
        if not self._skills:
            return ""

        lines = ["## Available Skills\n"]
        lines.append("You have the following specialized skills loaded. ")
        lines.append("When a user's request matches a skill's description, follow its instructions. ")
        lines.append("You can also use `/skill <name>` to explicitly activate a skill.\n")

        for skill in self._skills.values():
            if skill.model_invocable:
                lines.append(f"### Skill: {skill.name}")
                if skill.description:
                    lines.append(f"**When to use**: {skill.description}")
                if skill.body:
                    lines.append(skill.body)
                lines.append("")

        return "\n".join(lines)

    def get_skill_body(self, name: str) -> Optional[str]:
        """Get the full body content of a skill.

        Args:
            name: Skill name

        Returns:
            Skill body text if found, None otherwise
        """
        skill = self.get(name)
        return skill.body if skill else None

    def reload(
        self,
        user_skills_dir: Optional[Path] = None,
        project_skills_dir: Optional[Path] = None,
    ) -> int:
        """Reload all skills from disk.

        Args:
            user_skills_dir: User-level skills directory
            project_skills_dir: Project-level skills directory

        Returns:
            Number of skills loaded
        """
        return self.load(user_skills_dir, project_skills_dir)


# Global singleton
_registry: Optional[SkillRegistry] = None


def get_skill_registry() -> SkillRegistry:
    """Get or create the global skill registry singleton."""
    global _registry
    if _registry is None:
        _registry = SkillRegistry()
    return _registry
