"""权限规则工具语法测试（收敛批次③A，对齐 Claude Code `Tool(specifier)`）。

新增括号形态（与遗留 `tool:pattern` 并存）：
- `Bash(git diff:*)`   命令前缀匹配（`:*` 后缀）
- `Bash(ls -la)`       命令精确匹配
- `Edit(src/**)`       路径 glob（相对工作区；`~/` 家目录；`//` 绝对路径）
- `WebFetch(domain:example.com)`  域名匹配（含子域）
- 无 specifier 类的工具（含 mcp__）括号规则不命中
"""

import os


from mini_claude.permissions.rules import match_rule, parse_rules, primary_arg


class TestParseSpecifierForm:
    def test_paren_form_parsed(self):
        rules = parse_rules(["Bash(git diff:*)"])
        assert len(rules) == 1
        assert rules[0].tool == "Bash"
        assert rules[0].specifier == "git diff:*"

    def test_plain_paren_no_spec(self):
        rules = parse_rules(["Bash()"])
        assert rules and rules[0].specifier == ""

    def test_legacy_colon_form_unchanged(self):
        rules = parse_rules(["run_command:rm *"])
        assert rules[0].tool == "run_command" and rules[0].pattern == "rm *"
        assert rules[0].specifier is None

    def test_bare_name_unchanged(self):
        rules = parse_rules(["read_file"])
        assert rules[0].tool == "read_file" and rules[0].pattern is None


class TestCommandSpecifiers:
    def test_prefix_match(self):
        rules = parse_rules(["run_command(git diff:*)"])
        assert match_rule(rules[0], "run_command", {"command": "git diff HEAD~1"})
        assert not match_rule(rules[0], "run_command", {"command": "git push"})

    def test_exact_match(self):
        rules = parse_rules(["run_command(ls -la)"])
        assert match_rule(rules[0], "run_command", {"command": "ls -la"})
        assert not match_rule(rules[0], "run_command", {"command": "ls -la /tmp"})

    def test_background_tool_same_semantics(self):
        rules = parse_rules(["run_background(npm run build:*)"])
        assert match_rule(rules[0], "run_background", {"command": "npm run build --watch"})


class TestPathSpecifiers:
    def test_relative_glob_matches_workspace_path(self, tmp_path, monkeypatch):
        from mini_claude.config.settings import settings

        monkeypatch.setattr(settings, "workspace_root", str(tmp_path))
        rules = parse_rules(["edit_file(src/**)"])
        target = str(tmp_path / "src" / "a.py")
        assert match_rule(rules[0], "edit_file", {"path": target})
        assert not match_rule(rules[0], "edit_file", {"path": str(tmp_path / "docs" / "b.md")})

    def test_relative_exact(self, tmp_path, monkeypatch):
        from mini_claude.config.settings import settings

        monkeypatch.setattr(settings, "workspace_root", str(tmp_path))
        rules = parse_rules(["read_file(README.md)"])
        assert match_rule(rules[0], "read_file", {"path": str(tmp_path / "README.md")})

    def test_home_expansion(self):
        rules = parse_rules(["read_file(~/zshrc)"])
        home = os.path.expanduser("~")
        assert match_rule(rules[0], "read_file", {"path": f"{home}/zshrc"})
        assert not match_rule(rules[0], "read_file", {"path": "/etc/zshrc"})


class TestWebFetchDomain:
    def test_domain_match_with_subdomains(self):
        rules = parse_rules(["web_fetch(domain:example.com)"])
        assert match_rule(rules[0], "web_fetch", {"url": "https://example.com/a"})
        assert match_rule(rules[0], "web_fetch", {"url": "https://api.example.com/b"})
        assert not match_rule(rules[0], "web_fetch", {"url": "https://notexample.com/"})
        assert not match_rule(rules[0], "web_fetch", {"url": "https://other.org/"})

    def test_domain_requires_prefix_form(self):
        rules = parse_rules(["web_fetch(example.com)"])
        assert not match_rule(rules[0], "web_fetch", {"url": "https://example.com/"})


class TestLegacyStillWorks:
    def test_legacy_glob_on_primary_arg(self):
        rules = parse_rules(["run_command:rm *"])
        assert match_rule(rules[0], "run_command", {"command": "rm -rf /"})
        assert not match_rule(rules[0], "run_command", {"command": "ls"})

    def test_bare_name_matches_any_args(self):
        rules = parse_rules(["read_file"])
        assert match_rule(rules[0], "read_file", {"path": "任意"})

    def test_primary_arg_untouched(self):
        assert primary_arg("run_command", {"command": "ls"}) == "ls"
        assert primary_arg("read_file", {"path": "a"}) == "a"
