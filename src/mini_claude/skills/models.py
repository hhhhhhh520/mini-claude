"""Skill data model and frontmatter parsing."""

from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import yaml


@dataclass
class Skill:
    """A loaded skill with metadata and body content.

    Attributes:
        name: Skill identifier (matches directory name)
        description: When to trigger this skill
        body: Full markdown body content
        source_path: Path to the SKILL.md file
        user_invocable: Whether users can invoke via /skill command
        model_invocable: Whether the LLM can auto-invoke
    """

    name: str
    description: str
    body: str
    source_path: Path
    user_invocable: bool = True
    model_invocable: bool = True

    @property
    def summary(self) -> str:
        """One-line summary for display in skill lists."""
        desc = self.description.split("\n")[0][:80]
        return f"{self.name}: {desc}"


def parse_skill_file(path: Path) -> Optional[Skill]:
    """Parse a SKILL.md file into a Skill object.

    Expects YAML frontmatter delimited by --- lines, followed by markdown body.

    Args:
        path: Path to the SKILL.md file

    Returns:
        Skill object if parsing succeeds, None otherwise
    """
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return None

    return parse_skill_text(text, path)


def parse_skill_text(text: str, source_path: Path) -> Optional[Skill]:
    """Parse skill text with YAML frontmatter.

    Args:
        text: Full text content of SKILL.md
        source_path: Path to associate with the parsed skill

    Returns:
        Skill object if parsing succeeds, None otherwise
    """
    if not text.strip():
        return None

    # Split frontmatter from body
    parts = text.split("---", 2)
    if len(parts) < 3:
        # No valid frontmatter found; treat entire content as body
        # with name derived from directory
        name = source_path.parent.name if source_path.parent.name else "unknown"
        return Skill(
            name=name,
            description="",
            body=text.strip(),
            source_path=source_path,
        )

    frontmatter_str = parts[1].strip()
    body = parts[2].strip()

    try:
        meta = yaml.safe_load(frontmatter_str)
    except yaml.YAMLError:
        return None

    if not isinstance(meta, dict):
        return None

    name = meta.get("name", "")
    if not name:
        # Derive name from parent directory
        name = source_path.parent.name if source_path.parent.name else "unknown"

    description = meta.get("description", "")
    if not isinstance(description, str):
        description = str(description)

    user_invocable = meta.get("user-invocable", True)
    model_invocable = not meta.get("disable-model-invocation", False)

    return Skill(
        name=name,
        description=description,
        body=body,
        source_path=source_path,
        user_invocable=bool(user_invocable),
        model_invocable=bool(model_invocable),
    )
