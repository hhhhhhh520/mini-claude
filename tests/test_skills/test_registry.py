"""Tests for SkillRegistry."""

import pytest
from pathlib import Path

from mini_claude.skills.registry import SkillRegistry, get_skill_registry


@pytest.fixture
def skills_dir(tmp_path):
    """Create test skills directory."""
    for name, desc in [("alpha", "First skill"), ("beta", "Second skill")]:
        skill_file = tmp_path / name / "SKILL.md"
        skill_file.parent.mkdir(parents=True)
        skill_file.write_text(
            f"---\nname: {name}\ndescription: {desc}\n---\n# {name.title()}\nBody of {name}",
            encoding="utf-8",
        )
    return tmp_path


class TestSkillRegistry:
    """Test SkillRegistry class."""

    def test_load_skills(self, skills_dir):
        registry = SkillRegistry()
        count = registry.load(user_skills_dir=skills_dir)
        assert count == 2

    def test_get_by_name(self, skills_dir):
        registry = SkillRegistry()
        registry.load(user_skills_dir=skills_dir)
        skill = registry.get("alpha")
        assert skill is not None
        assert skill.name == "alpha"

    def test_get_nonexistent(self, skills_dir):
        registry = SkillRegistry()
        registry.load(user_skills_dir=skills_dir)
        assert registry.get("nonexistent") is None

    def test_list_skills(self, skills_dir):
        registry = SkillRegistry()
        registry.load(user_skills_dir=skills_dir)
        skills = registry.list_skills()
        assert len(skills) == 2

    def test_is_loaded(self):
        registry = SkillRegistry()
        assert registry.is_loaded() is False
        registry.load(user_skills_dir=Path("/nonexistent"))
        assert registry.is_loaded() is True

    def test_reload(self, skills_dir):
        registry = SkillRegistry()
        registry.load(user_skills_dir=skills_dir)
        assert len(registry.list_skills()) == 2

        # Add a new skill
        skill_file = skills_dir / "gamma" / "SKILL.md"
        skill_file.parent.mkdir(parents=True)
        skill_file.write_text(
            "---\nname: gamma\ndescription: Third\n---\nBody",
            encoding="utf-8",
        )

        count = registry.reload(user_skills_dir=skills_dir)
        assert count == 3

    def test_get_skill_prompt(self, skills_dir):
        registry = SkillRegistry()
        registry.load(user_skills_dir=skills_dir)
        prompt = registry.get_skill_prompt()
        assert "alpha" in prompt
        assert "beta" in prompt
        assert "Available Skills" in prompt

    def test_get_skill_prompt_empty(self):
        registry = SkillRegistry()
        registry.load(user_skills_dir=Path("/nonexistent"))
        assert registry.get_skill_prompt() == ""

    def test_get_skill_body(self, skills_dir):
        registry = SkillRegistry()
        registry.load(user_skills_dir=skills_dir)
        body = registry.get_skill_body("alpha")
        assert body is not None
        assert "Body of alpha" in body

    def test_get_skill_body_nonexistent(self, skills_dir):
        registry = SkillRegistry()
        registry.load(user_skills_dir=skills_dir)
        assert registry.get_skill_body("nonexistent") is None


class TestGetSkillRegistry:
    """Test global singleton."""

    def test_returns_same_instance(self):
        r1 = get_skill_registry()
        r2 = get_skill_registry()
        assert r1 is r2
