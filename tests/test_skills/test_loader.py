"""Tests for skill discovery and loading."""

import pytest

from mini_claude.skills.loader import discover_skills, load_skills_from_dir, load_skill_from_file


@pytest.fixture
def skills_dir(tmp_path):
    """Create a temporary skills directory with test skills."""
    # Skill 1
    skill1 = tmp_path / "hello" / "SKILL.md"
    skill1.parent.mkdir(parents=True)
    skill1.write_text(
        "---\nname: hello\ndescription: Say hello\n---\n# Hello\nSay hello to the user",
        encoding="utf-8",
    )

    # Skill 2
    skill2 = tmp_path / "goodbye" / "SKILL.md"
    skill2.parent.mkdir(parents=True)
    skill2.write_text(
        "---\nname: goodbye\ndescription: Say goodbye\n---\n# Goodbye\nFarewell message",
        encoding="utf-8",
    )

    # Invalid skill (no frontmatter parsing possible — actually this will work with fallback)
    skill3 = tmp_path / "broken" / "SKILL.md"
    skill3.parent.mkdir(parents=True)
    skill3.write_text("", encoding="utf-8")

    # Not a skill directory (no SKILL.md)
    (tmp_path / "not-a-skill" / "other.txt").parent.mkdir(parents=True)
    (tmp_path / "not-a-skill" / "other.txt").write_text("not a skill", encoding="utf-8")

    return tmp_path


class TestLoadSkillsFromDir:
    """Test load_skills_from_dir function."""

    def test_loads_valid_skills(self, skills_dir):
        skills = load_skills_from_dir(skills_dir)
        names = {s.name for s in skills}
        assert "hello" in names
        assert "goodbye" in names

    def test_skips_empty_skill_files(self, skills_dir):
        skills = load_skills_from_dir(skills_dir)
        names = {s.name for s in skills}
        # "broken" has empty content, parse_skill_text returns None for empty
        assert "broken" not in names

    def test_skips_directories_without_skill_md(self, skills_dir):
        skills = load_skills_from_dir(skills_dir)
        names = {s.name for s in skills}
        assert "not-a-skill" not in names

    def test_nonexistent_directory(self, tmp_path):
        skills = load_skills_from_dir(tmp_path / "nonexistent")
        assert skills == []

    def test_empty_directory(self, tmp_path):
        skills = load_skills_from_dir(tmp_path)
        assert skills == []


class TestDiscoverSkills:
    """Test discover_skills function."""

    def test_user_level_only(self, skills_dir):
        skills = discover_skills(user_skills_dir=skills_dir)
        assert len(skills) >= 2

    def test_project_overrides_user(self, tmp_path):
        # User has "hello" skill
        user_dir = tmp_path / "user_skills"
        (user_dir / "hello").mkdir(parents=True)
        (user_dir / "hello" / "SKILL.md").write_text(
            "---\nname: hello\ndescription: User version\n---\nUser body",
            encoding="utf-8",
        )

        # Project has "hello" skill with different description
        project_dir = tmp_path / "project_skills"
        (project_dir / "hello").mkdir(parents=True)
        (project_dir / "hello" / "SKILL.md").write_text(
            "---\nname: hello\ndescription: Project version\n---\nProject body",
            encoding="utf-8",
        )

        skills = discover_skills(user_skills_dir=user_dir, project_skills_dir=project_dir)
        hello = [s for s in skills if s.name == "hello"]
        assert len(hello) == 1
        assert hello[0].description == "Project version"

    def test_no_project_dir(self, skills_dir):
        skills = discover_skills(user_skills_dir=skills_dir, project_skills_dir=None)
        assert len(skills) >= 2


class TestLoadSkillFromFile:
    """Test load_skill_from_file function."""

    def test_load_valid_file(self, tmp_path):
        skill_file = tmp_path / "SKILL.md"
        skill_file.write_text(
            "---\nname: test\ndescription: Test\n---\nBody",
            encoding="utf-8",
        )
        skill = load_skill_from_file(skill_file)
        assert skill is not None
        assert skill.name == "test"

    def test_load_empty_file(self, tmp_path):
        skill_file = tmp_path / "SKILL.md"
        skill_file.write_text("", encoding="utf-8")
        skill = load_skill_from_file(skill_file)
        assert skill is None
