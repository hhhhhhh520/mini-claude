"""Skills system for Mini Claude Code.

Provides skill loading, registration, and invocation through
slash commands and automatic description matching.
"""

from .models import Skill
from .loader import discover_skills, load_skill_from_file
from .registry import SkillRegistry, get_skill_registry

__all__ = [
    "Skill",
    "discover_skills",
    "load_skill_from_file",
    "SkillRegistry",
    "get_skill_registry",
]
