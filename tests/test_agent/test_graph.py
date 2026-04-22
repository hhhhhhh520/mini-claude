"""Tests for agent state and graph."""

import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from langchain_core.messages import HumanMessage, SystemMessage, AIMessage

from mini_claude.agent.state import AgentState, create_initial_state
from mini_claude.agent.nodes import think_node, should_continue_router


# ========== AgentState Tests (15个) ==========

class TestAgentStateCreation:
    """测试 AgentState 创建 - 15个测试用例"""

    def test_create_initial_state_basic(self):
        """测试创建基本初始状态"""
        state = create_initial_state("Hello", thread_id="test")
        assert state["current_task"] == "Hello"
        assert state["thread_id"] == "test"
        assert state["iteration"] == 0
        assert state["should_continue"] is True

    def test_create_initial_state_with_history(self):
        """测试带历史消息创建状态"""
        history = [HumanMessage(content="Previous message")]
        state = create_initial_state("New message", history=history, thread_id="test")
        assert len(state["messages"]) == 2

    def test_create_initial_state_empty_input(self):
        """测试空输入创建状态"""
        state = create_initial_state("", thread_id="test")
        assert state["current_task"] == ""

    def test_create_initial_state_long_input(self):
        """测试长输入创建状态"""
        long_input = "测试内容" * 1000
        state = create_initial_state(long_input, thread_id="test")
        assert state["current_task"] == long_input

    def test_create_initial_state_unicode(self):
        """测试 Unicode 输入"""
        unicode_input = "中文 English 日本語 한국어"
        state = create_initial_state(unicode_input, thread_id="test")
        assert state["current_task"] == unicode_input

    def test_create_initial_state_special_chars(self):
        """测试特殊字符输入"""
        special_input = "Hello\nWorld\tTab@#$%"
        state = create_initial_state(special_input, thread_id="test")
        assert state["current_task"] == special_input

    def test_create_initial_state_subagent_mode(self):
        """测试子代理模式"""
        state = create_initial_state("Task", thread_id="test", is_subagent=True)
        assert state["is_subagent"] is True

    def test_create_initial_state_allowed_tools(self):
        """测试允许的工具列表"""
        allowed = ["read_file", "write_file"]
        state = create_initial_state("Task", thread_id="test", allowed_tools=allowed)
        assert state["allowed_tools"] == allowed

    def test_create_initial_state_default_thread_id(self):
        """测试默认线程ID"""
        state = create_initial_state("Task")
        assert state["thread_id"] == "default"

    def test_create_initial_state_messages_count(self):
        """测试消息数量"""
        state = create_initial_state("Task", thread_id="test")
        assert len(state["messages"]) == 1

    def test_create_initial_state_plan_none(self):
        """测试计划初始为空"""
        state = create_initial_state("Task", thread_id="test")
        assert state["plan"] is None

    def test_create_initial_state_tool_results_empty(self):
        """测试工具结果初始为空"""
        state = create_initial_state("Task", thread_id="test")
        assert state["tool_results"] == []

    def test_create_initial_state_sub_agents_empty(self):
        """测试子代理初始为空"""
        state = create_initial_state("Task", thread_id="test")
        assert state["sub_agents"] == {}

    def test_create_initial_state_errors_none(self):
        """测试错误初始为空"""
        state = create_initial_state("Task", thread_id="test")
        assert state["errors"] is None

    def test_create_initial_state_counters_zero(self):
        """测试计数器初始为零"""
        state = create_initial_state("Task", thread_id="test")
        assert state["incomplete_check_count"] == 0
        assert state["consecutive_read_only_count"] == 0
        assert state["no_tool_call_count"] == 0


# ========== Router Tests (10个) ==========

class TestShouldContinueRouter:
    """测试路由器 - 10个测试用例"""

    def test_router_should_continue_true(self):
        """测试继续为True"""
        state = AgentState(should_continue=True)
        assert should_continue_router(state) is True

    def test_router_should_continue_false(self):
        """测试继续为False"""
        state = AgentState(should_continue=False)
        assert should_continue_router(state) is False

    def test_router_with_messages(self):
        """测试带消息的路由"""
        state = AgentState(
            messages=[HumanMessage(content="test")],
            should_continue=True
        )
        assert should_continue_router(state) is True

    def test_router_with_iteration(self):
        """测试带迭代计数的路由"""
        state = AgentState(
            iteration=5,
            should_continue=True
        )
        assert should_continue_router(state) is True

    def test_router_with_tool_results(self):
        """测试带工具结果的路由"""
        state = AgentState(
            tool_results=[{"result": "success"}],
            should_continue=False
        )
        assert should_continue_router(state) is False

    def test_router_with_sub_agents(self):
        """测试带子代理的路由"""
        state = AgentState(
            sub_agents={"agent1": "running"},
            should_continue=True
        )
        assert should_continue_router(state) is True

    def test_router_with_errors(self):
        """测试带错误的路由"""
        state = AgentState(
            errors=["Some error"],
            should_continue=True
        )
        assert should_continue_router(state) is True

    def test_router_with_plan(self):
        """测试带计划的路由"""
        state = AgentState(
            plan=["Step 1", "Step 2"],
            should_continue=True
        )
        assert should_continue_router(state) is True

    def test_router_state_immutability(self):
        """测试路由不修改状态"""
        state = AgentState(should_continue=True)
        _ = should_continue_router(state)
        assert state["should_continue"] is True

    def test_router_multiple_calls(self):
        """测试多次调用路由"""
        state = AgentState(should_continue=True)
        for _ in range(10):
            assert should_continue_router(state) is True


# ========== Think Node Tests (10个) ==========

class TestThinkNode:
    """测试思考节点 - 10个测试用例"""

    @pytest.mark.asyncio
    async def test_think_node_basic(self):
        """测试基本思考节点"""
        state = create_initial_state("Test task")
        result = await think_node(state)
        assert result["iteration"] == 1
        assert len(result["messages"]) > 0

    @pytest.mark.asyncio
    async def test_think_node_adds_system_message(self):
        """测试添加系统消息"""
        state = create_initial_state("Test task")
        result = await think_node(state)
        assert any(isinstance(m, SystemMessage) for m in result["messages"])

    @pytest.mark.asyncio
    async def test_think_node_increments_iteration(self):
        """测试迭代计数增加"""
        state = create_initial_state("Test task")
        state["iteration"] = 5
        result = await think_node(state)
        assert result["iteration"] == 6

    @pytest.mark.asyncio
    async def test_think_node_preserves_messages(self):
        """测试保留原有消息"""
        state = create_initial_state("Test task")
        original_count = len(state["messages"])
        result = await think_node(state)
        assert len(result["messages"]) > original_count

    @pytest.mark.asyncio
    async def test_think_node_with_history(self):
        """测试带历史消息"""
        history = [HumanMessage(content="Previous")]
        state = create_initial_state("New", history=history, thread_id="test")
        result = await think_node(state)
        assert len(result["messages"]) >= 2

    @pytest.mark.asyncio
    async def test_think_node_empty_task(self):
        """测试空任务"""
        state = create_initial_state("")
        result = await think_node(state)
        assert result["iteration"] == 1

    @pytest.mark.asyncio
    async def test_think_node_long_task(self):
        """测试长任务"""
        long_task = "测试" * 1000
        state = create_initial_state(long_task)
        result = await think_node(state)
        assert result["iteration"] == 1

    @pytest.mark.asyncio
    async def test_think_node_unicode_task(self):
        """测试 Unicode 任务"""
        unicode_task = "中文任务测试"
        state = create_initial_state(unicode_task)
        result = await think_node(state)
        assert result["iteration"] == 1

    @pytest.mark.asyncio
    async def test_think_node_subagent_mode(self):
        """测试子代理模式"""
        state = create_initial_state("Task", is_subagent=True)
        result = await think_node(state)
        assert result["is_subagent"] is True

    @pytest.mark.asyncio
    async def test_think_node_multiple_iterations(self):
        """测试多次迭代"""
        state = create_initial_state("Task")
        for i in range(3):
            state = await think_node(state)
            assert state["iteration"] == i + 1


# ========== State Transition Tests (15个) ==========

class TestStateTransitions:
    """测试状态转换 - 15个测试用例"""

    def test_state_transition_messages_append(self):
        """测试消息追加"""
        state = create_initial_state("Task")
        state["messages"].append(AIMessage(content="Response"))
        assert len(state["messages"]) == 2

    def test_state_transition_tool_results_append(self):
        """测试工具结果追加"""
        state = create_initial_state("Task")
        state["tool_results"].append({"tool": "test", "result": "ok"})
        assert len(state["tool_results"]) == 1

    def test_state_transition_sub_agents_update(self):
        """测试子代理更新"""
        state = create_initial_state("Task")
        state["sub_agents"]["agent1"] = "running"
        assert state["sub_agents"]["agent1"] == "running"

    def test_state_transition_sub_agent_results(self):
        """测试子代理结果"""
        state = create_initial_state("Task")
        state["sub_agent_results"]["agent1"] = {"output": "done"}
        assert state["sub_agent_results"]["agent1"]["output"] == "done"

    def test_state_transition_plan_set(self):
        """测试计划设置"""
        state = create_initial_state("Task")
        state["plan"] = ["Step 1", "Step 2", "Step 3"]
        assert len(state["plan"]) == 3

    def test_state_transition_errors_append(self):
        """测试错误追加"""
        state = create_initial_state("Task")
        state["errors"] = []
        state["errors"].append("Error 1")
        assert len(state["errors"]) == 1

    def test_state_transition_should_continue_toggle(self):
        """测试继续标志切换"""
        state = create_initial_state("Task")
        assert state["should_continue"] is True
        state["should_continue"] = False
        assert state["should_continue"] is False

    def test_state_transition_iteration_increment(self):
        """测试迭代递增"""
        state = create_initial_state("Task")
        for i in range(10):
            state["iteration"] = i + 1
        assert state["iteration"] == 10

    def test_state_transition_incomplete_check_increment(self):
        """测试不完整检查计数"""
        state = create_initial_state("Task")
        state["incomplete_check_count"] = 1
        state["incomplete_check_count"] += 1
        assert state["incomplete_check_count"] == 2

    def test_state_transition_last_missing_files(self):
        """测试缺失文件记录"""
        state = create_initial_state("Task")
        state["last_missing_files"] = ["file1.py", "file2.py"]
        assert len(state["last_missing_files"]) == 2

    def test_state_transition_read_only_count(self):
        """测试只读计数"""
        state = create_initial_state("Task")
        state["consecutive_read_only_count"] = 3
        assert state["consecutive_read_only_count"] == 3

    def test_state_transition_last_tool_names(self):
        """测试工具名称记录"""
        state = create_initial_state("Task")
        state["last_tool_names"] = ["read_file", "search_content"]
        assert "read_file" in state["last_tool_names"]

    def test_state_transition_no_tool_call_count(self):
        """测试无工具调用计数"""
        state = create_initial_state("Task")
        state["no_tool_call_count"] = 2
        assert state["no_tool_call_count"] == 2

    def test_state_transition_pending_tool_calls(self):
        """测试待执行工具调用"""
        state = create_initial_state("Task")
        state["pending_tool_calls"] = [{"name": "read_file", "args": {}}]
        assert len(state["pending_tool_calls"]) == 1

    def test_state_transition_allowed_tools(self):
        """测试允许工具列表"""
        state = create_initial_state("Task", allowed_tools=["read_file"])
        state["allowed_tools"].append("write_file")
        assert "write_file" in state["allowed_tools"]
