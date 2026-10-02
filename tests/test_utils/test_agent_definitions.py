"""可定义子代理测试（收敛批次③B）：定义加载 + spawn 接线。"""

from types import SimpleNamespace

import pytest

from mini_claude.utils import agent_definitions as ad


@pytest.fixture(autouse=True)
def clean_registry_env():
    yield


def _write_agent(base, name, frontmatter, body):
    d = base / ".mini-claude" / "agents"
    d.mkdir(parents=True, exist_ok=True)
    (d / f"{name}.md").write_text(f"---\n{frontmatter}---\n{body}", encoding="utf-8")


class TestLoadDefinitions:
    def test_frontmatter_and_body_parsed(self, tmp_path):
        _write_agent(
            tmp_path,
            "reviewer",
            "name: reviewer\ndescription: 审查代码\ntools: read_file, search_content\n",
            "你是代码审查员。",
        )
        defs = ad.load_agent_definitions(workspace_root=str(tmp_path))
        assert "reviewer" in defs
        d = defs["reviewer"]
        assert d.description == "审查代码"
        assert d.body == "你是代码审查员。"
        assert d.tools == ["read_file", "search_content"]

    def test_default_tools_when_omitted(self, tmp_path):
        _write_agent(tmp_path, "generic", "name: generic\n", "通用助手")
        d = ad.load_agent_definitions(workspace_root=str(tmp_path))["generic"]
        assert d.tools, "缺省应回退默认白名单"
        assert "read_file" in d.tools

    def test_unknown_tool_filtered_with_warning(self, tmp_path):
        _write_agent(tmp_path, "broken", "name: broken\ntools: read_file, no_such_tool\n", "b")
        d = ad.load_agent_definitions(workspace_root=str(tmp_path))["broken"]
        assert d.tools == ["read_file"], "拼错的工具名不得静默进白名单"

    def test_project_overrides_user(self, tmp_path, monkeypatch):
        _write_agent(tmp_path, "shared", "name: shared\ndescription: 项目版\n", "项目正文")
        home = tmp_path / "home"
        home.mkdir()
        _write_agent(home, "shared", "name: shared\ndescription: 用户版\n", "用户正文")
        monkeypatch.setattr("pathlib.Path.home", lambda: home)
        d = ad.load_agent_definitions(workspace_root=str(tmp_path), home_dir=str(home))
        assert d["shared"].description == "项目版"

    def test_model_field_rejected_with_warning(self, tmp_path):
        _write_agent(tmp_path, "m", "name: m\nmodel: some-model\n", "b")
        d = ad.load_agent_definitions(workspace_root=str(tmp_path))["m"]
        assert d.body == "b"  # 解析不炸；model 记 warning 忽略


class TestSpawnWiring:
    @pytest.mark.asyncio
    async def test_unknown_agent_type_errors(self, tmp_path, monkeypatch):
        from mini_claude.config.settings import settings
        from mini_claude.tools.agent_spawn import SpawnAgentTool

        monkeypatch.setattr(settings, "workspace_root", str(tmp_path))
        result = await SpawnAgentTool().execute(task="x", agent_type="nope")
        assert result.startswith("Error") and "nope" in result

    @pytest.mark.asyncio
    async def test_custom_agent_uses_body_and_tools(self, tmp_path, monkeypatch):
        """命中定义：prompt 用正文拼装、白名单用定义的 tools。"""
        from mini_claude.config.settings import settings
        from mini_claude.tools.agent_spawn import SpawnAgentTool

        _write_agent(
            tmp_path,
            "reader",
            "name: reader\ndescription: 只读\ntools: read_file, list_dir\n",
            "你只做只读分析。",
        )
        monkeypatch.setattr(settings, "workspace_root", str(tmp_path))

        captured = {}

        async def fake_ainvoke(state, config=None):
            captured["prompt"] = state["current_task"]
            captured["allowed_tools"] = state["allowed_tools"]
            return {"messages": []}

        import mini_claude.agent.graph as graph_mod

        monkeypatch.setattr(
            graph_mod,
            "build_agent_graph_no_checkpoint",
            lambda: SimpleNamespace(ainvoke=fake_ainvoke),
        )

        result = await SpawnAgentTool().execute(
            task="审查模块", agent_type="reader", agent_id="cap_001"
        )
        assert "Spawned sub-agent" in result
        # spawn 是异步任务：等它跑完再断言捕获
        import asyncio

        from mini_claude.agent.subagent import subagent_manager

        for _ in range(50):
            if captured:
                break
            await asyncio.sleep(0.05)
        await subagent_manager.wait_for_one("cap_001")
        assert "你只做只读分析。" in captured["prompt"]
        assert "审查模块" in captured["prompt"]
        assert captured["allowed_tools"] == ["read_file", "list_dir"]

    def test_available_names_dynamic_description(self, tmp_path, monkeypatch):
        from mini_claude.config.settings import settings
        from mini_claude.tools.agent_spawn import SpawnAgentTool

        _write_agent(tmp_path, "reader", "name: reader\n", "b")
        monkeypatch.setattr(settings, "workspace_root", str(tmp_path))
        desc = SpawnAgentTool().description
        assert "reader" in desc
