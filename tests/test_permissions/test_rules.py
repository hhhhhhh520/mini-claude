"""权限规则解析与匹配测试（P3-2）

规则形态：`工具名`（仅按名匹配）/ `工具名:模式`（对主参数做 glob 匹配）。
"""

import pytest

from mini_claude.permissions.rules import Rule, parse_rules, match_rule, primary_arg


class TestParseRules:
    def test_name_only_rule(self):
        rules = parse_rules(["read_file"])
        assert rules[0].tool == "read_file"
        assert rules[0].pattern is None

    def test_rule_with_pattern(self):
        rules = parse_rules(["run_command:git *"])
        assert rules[0].tool == "run_command"
        assert rules[0].pattern == "git *"

    def test_empty_and_invalid_skipped(self):
        rules = parse_rules(["", "  ", ":nocolon", 123, "ok_rule"])
        assert [r.tool for r in rules] == ["ok_rule"]

    def test_pattern_with_colon_inside(self):
        """模式里可以再带冒号（如路径），按第一个冒号切分"""
        rules = parse_rules(["read_file:C:/data/*"])
        assert rules[0].tool == "read_file"
        assert rules[0].pattern == "C:/data/*"


class TestPrimaryArg:
    def test_command_tools(self):
        assert primary_arg("run_command", {"command": "ls -la"}) == "ls -la"
        assert primary_arg("run_background", {"command": "server"}) == "server"

    def test_file_tools(self):
        assert primary_arg("write_file", {"path": "a.py"}) == "a.py"
        assert primary_arg("edit_file", {"path": "a.py"}) == "a.py"

    def test_unknown_tool_returns_empty(self):
        assert primary_arg("mcp__fs__read", {"path": "x"}) == ""

    def test_missing_arg_returns_empty(self):
        assert primary_arg("run_command", {}) == ""


class TestMatchRule:
    def test_name_only_matches_any_args(self):
        rule = Rule(tool="read_file", pattern=None)
        assert match_rule(rule, "read_file", {"path": "anything"})
        assert not match_rule(rule, "write_file", {})

    def test_pattern_glob_match(self):
        rule = Rule(tool="run_command", pattern="git *")
        assert match_rule(rule, "run_command", {"command": "git status"})
        assert not match_rule(rule, "run_command", {"command": "gitx status"})
        assert not match_rule(rule, "run_command", {"command": "hg status"})

    def test_pattern_no_wildcard_is_exact(self):
        rule = Rule(tool="run_command", pattern="git status")
        assert match_rule(rule, "run_command", {"command": "git status"})
        assert not match_rule(rule, "run_command", {"command": "git status -s"})

    def test_pattern_with_trailing_star_matches_prefix(self):
        rule = Rule(tool="run_command", pattern="git*")
        assert match_rule(rule, "run_command", {"command": "github-cli x"})

    def test_case_sensitive(self):
        rule = Rule(tool="run_command", pattern="GIT *")
        assert not match_rule(rule, "run_command", {"command": "git status"})

    def test_pattern_but_empty_primary_arg(self):
        rule = Rule(tool="write_file", pattern="*")
        assert match_rule(rule, "write_file", {})  # 空 arg 也被 * 匹配

    def test_mcp_tool_name_only_rule(self):
        rule = Rule(tool="mcp__fs__read", pattern=None)
        assert match_rule(rule, "mcp__fs__read", {"path": "x"})


class TestParseRulesListRoundtrip:
    def test_full_config_shape(self):
        rules = parse_rules(["read_file", "run_command:git *", "write_file:/tmp/*"])
        assert len(rules) == 3


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
