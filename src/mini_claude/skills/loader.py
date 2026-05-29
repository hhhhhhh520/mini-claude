"""Skill discovery and loading from filesystem."""

import logging
from pathlib import Path
from typing import List, Optional

from .models import Skill, parse_skill_file

logger = logging.getLogger(__name__)

# Default skill directory name
SKILL_DIR_NAME = "skills"
SKILL_FILE_NAME = "SKILL.md"


def discover_skills(
    user_skills_dir: Optional[Path] = None,
    project_skills_dir: Optional[Path] = None,
) -> List[Skill]:
    """Discover skills from user-level and project-level directories.

    Scans for SKILL.md files in subdirectories of each skills directory.
    Project-level skills take precedence over user-level skills with the same name.

    Args:
        user_skills_dir: User-level skills directory (default: ~/.mini-claude/skills)
        project_skills_dir: Project-level skills directory (default: <workspace>/skills)

    Returns:
        List of discovered Skill objects
    """
    skills: dict[str, Skill] = {}

    # User-level skills
    if user_skills_dir is None:
        user_skills_dir = Path.home() / ".mini-claude" / SKILL_DIR_NAME

    for skill in load_skills_from_dir(user_skills_dir):
        skills[skill.name] = skill

    # Project-level skills (override user-level)
    if project_skills_dir is not None:
        for skill in load_skills_from_dir(project_skills_dir):
            skills[skill.name] = skill

    return list(skills.values())


def load_skills_from_dir(directory: Path) -> List[Skill]:
    """Load all skills from a directory.

    Each skill lives in a subdirectory containing a SKILL.md file.
    Example: skills/my-skill/SKILL.md

    Args:
        directory: Path to the skills directory

    Returns:
        List of Skill objects found
    """
    skills = []

    if not directory.is_dir():
        return skills

    for entry in sorted(directory.iterdir()):
        if not entry.is_dir():
            continue

        skill_file = entry / SKILL_FILE_NAME
        if skill_file.is_file():
            skill = load_skill_from_file(skill_file)
            if skill is not None:
                skills.append(skill)

    return skills


def load_skill_from_file(path: Path) -> Optional[Skill]:
    """Load a single skill from a SKILL.md file.

    Args:
        path: Path to the SKILL.md file

    Returns:
        Skill object if loading succeeds, None otherwise
    """
    skill = parse_skill_file(path)
    if skill is not None:
        logger.debug("Loaded skill: %s from %s", skill.name, path)
    else:
        logger.warning("Failed to parse skill file: %s", path)
    return skill
