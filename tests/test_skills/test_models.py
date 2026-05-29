"""Tests for Skill data model and frontmatter parsing."""

import pytest
from pathlib import Path

from mini_claude.skills.models import Skill, parse_skill_file, parse_skill_text


class TestParseSkillText:
    """Test parse_skill_text function."""

    def test_valid_frontmatter(self):
        text = "---\nname: test-skill\ndescription: A test skill\n---\n# Body\nContent here"
        skill = parse_skill_text(text, Path("/test/SKILL.md"))
        assert skill is not None
        assert skill.name == "test-skill"
        assert skill.description == "A test skill"
        assert "# Body" in skill.body
        assert "Content here" in skill.body

    def test_frontmatter_with_quotes(self):
        text = '---\nname: my-skill\ndescription: "Quoted description"\n---\nBody text'
        skill = parse_skill_text(text, Path("/test/SKILL.md"))
        assert skill is not None
        assert skill.description == "Quoted description"

    def test_multiline_description(self):
        text = "---\nname: multi\ndescription: |\n  Line one\n  Line two\n---\nBody"
        skill = parse_skill_text(text, Path("/test/SKILL.md"))
        assert skill is not None
        assert "Line one" in skill.description

    def test_no_frontmatter(self):
        text = "# Just a markdown file\nNo frontmatter here"
        skill = parse_skill_text(text, Path("/some/dir/SKILL.md"))
        assert skill is not None
        assert skill.name == "dir"  # derived from parent directory
        assert skill.description == ""
        assert "# Just a markdown file" in skill.body

    def test_empty_frontmatter(self):
        text = "---\n---\nBody content"
        skill = parse_skill_text(text, Path("/test/SKILL.md"))
        # Empty frontmatter yaml returns None, so parsing fails
        assert skill is None

    def test_empty_body(self):
        text = "---\nname: empty\ndescription: Has no body\n---\n"
        skill = parse_skill_text(text, Path("/test/SKILL.md"))
        assert skill is not None
        assert skill.name == "empty"

    def test_disable_model_invocation(self):
        text = "---\nname: deploy\ndescription: Deploy skill\ndisable-model-invocation: true\n---\nBody"
        skill = parse_skill_text(text, Path("/test/SKILL.md"))
        assert skill is not None
        assert skill.model_invocable is False
        assert skill.user_invocable is True

    def test_user_invocable_false(self):
        text = "---\nname: bg\ndescription: Background skill\nuser-invocable: false\n---\nBody"
        skill = parse_skill_text(text, Path("/test/SKILL.md"))
        assert skill is not None
        assert skill.user_invocable is False

    def test_empty_text_returns_none(self):
        assert parse_skill_text("", Path("/test/SKILL.md")) is None
        assert parse_skill_text("   ", Path("/test/SKILL.md")) is None

    def test_invalid_yaml_returns_none(self):
        text = "---\nname: [\ninvalid yaml\n---\nBody"
        assert parse_skill_text(text, Path("/test/SKILL.md")) is None

    def test_non_dict_yaml_returns_none(self):
        text = "---\n- item1\n- item2\n---\nBody"
        assert parse_skill_text(text, Path("/test/SKILL.md")) is None


class TestSkillDataclass:
    """Test Skill dataclass properties."""

    def test_summary(self):
        skill = Skill(
            name="test",
            description="Short description",
            body="body",
            source_path=Path("/test/SKILL.md"),
        )
        assert skill.summary == "test: Short description"

    def test_summary_truncates_long_description(self):
        long_desc = "A" * 200
        skill = Skill(
            name="test",
            description=long_desc,
            body="body",
            source_path=Path("/test/SKILL.md"),
        )
        assert len(skill.summary) <= 90  # name + ": " + 80 chars

    def test_summary_multiline_description(self):
        skill = Skill(
            name="test",
            description="First line\nSecond line",
            body="body",
            source_path=Path("/test/SKILL.md"),
        )
        assert skill.summary == "test: First line"

    def test_defaults(self):
        skill = Skill(
            name="test",
            description="",
            body="",
            source_path=Path("/test"),
        )
        assert skill.user_invocable is True
        assert skill.model_invocable is True


class TestParseSkillFile:
    """Test parse_skill_file with real files."""

    def test_parse_existing_file(self, tmp_path):
        skill_file = tmp_path / "test-skill" / "SKILL.md"
        skill_file.parent.mkdir(parents=True)
        skill_file.write_text(
            "---\nname: test\ndescription: Test skill\n---\n# Test\nBody",
            encoding="utf-8",
        )
        skill = parse_skill_file(skill_file)
        assert skill is not None
        assert skill.name == "test"

    def test_parse_nonexistent_file(self):
        skill = parse_skill_file(Path("/nonexistent/SKILL.md"))
        assert skill is None

    def test_parse_directory_instead_of_file(self, tmp_path):
        skill = parse_skill_file(tmp_path)
        assert skill is None
