"""Tests for agent state and graph - Updated for refactored state."""

import pytest
from langchain_core.messages import HumanMessage, SystemMessage, AIMessage

from mini_claude.agent.state import AgentState, StopReason, create_initial_state
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
        assert state["stop_reason"] == StopReason.CONTINUE

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

    def test_create_initial_state_retry_count_zero(self):
        """测试重试计数初始为零"""
        state = create_initial_state("Task", thread_id="test")
        assert state["retry_count"] == 0

    def test_create_initial_state_sub_agents_empty(self):
        """测试子代理初始为空"""
        state = create_initial_state("Task", thread_id="test")
        assert state["sub_agents"] == {}

    def test_create_initial_state_errors_empty(self):
        """测试错误初始为空列表"""
        state = create_initial_state("Task", thread_id="test")
        assert state["errors"] == []

    def test_create_initial_state_stop_reason_continue(self):
        """测试停止原因初始为 CONTINUE"""
        state = create_initial_state("Task", thread_id="test")
        assert state["stop_reason"] == StopReason.CONTINUE

    def test_create_initial_state_sub_agent_results_empty(self):
        """测试子代理结果初始为空"""
        state = create_initial_state("Task", thread_id="test")
        assert state["sub_agent_results"] == {}


# ========== Router Tests (10个) ==========


class TestShouldContinueRouter:
    """测试路由器 - 10个测试用例"""

    def test_router_should_continue_true(self):
        """测试继续为True"""
        state = AgentState(
            messages=[],
            current_task="test",
            iteration=0,
            stop_reason=StopReason.CONTINUE,
            thread_id="test",
            sub_agents={},
            sub_agent_results={},
            is_subagent=False,
            errors=[],
            retry_count=0,
        )
        assert should_continue_router(state) is True

    def test_router_should_continue_false(self):
        """测试继续为False"""
        state = AgentState(
            messages=[],
            current_task="test",
            iteration=0,
            stop_reason=StopReason.TASK_COMPLETE,
            thread_id="test",
            sub_agents={},
            sub_agent_results={},
            is_subagent=False,
            errors=[],
            retry_count=0,
        )
        assert should_continue_router(state) is False

    def test_router_with_messages(self):
        """测试带消息的路由"""
        state = AgentState(
            messages=[HumanMessage(content="test")],
            current_task="test",
            iteration=0,
            stop_reason=StopReason.CONTINUE,
            thread_id="test",
            sub_agents={},
            sub_agent_results={},
            is_subagent=False,
            errors=[],
            retry_count=0,
        )
        assert should_continue_router(state) is True

    def test_router_with_iteration(self):
        """测试带迭代计数的路由"""
        state = AgentState(
            messages=[],
            current_task="test",
            iteration=5,
            stop_reason=StopReason.CONTINUE,
            thread_id="test",
            sub_agents={},
            sub_agent_results={},
            is_subagent=False,
            errors=[],
            retry_count=0,
        )
        assert should_continue_router(state) is True

    def test_router_with_stop_reason_error(self):
        """测试停止原因为错误"""
        state = AgentState(
            messages=[],
            current_task="test",
            iteration=0,
            stop_reason=StopReason.ERROR,
            thread_id="test",
            sub_agents={},
            sub_agent_results={},
            is_subagent=False,
            errors=["error"],
            retry_count=0,
        )
        assert should_continue_router(state) is False

    def test_router_with_sub_agents(self):
        """测试带子代理的路由"""
        state = AgentState(
            messages=[],
            current_task="test",
            iteration=0,
            stop_reason=StopReason.CONTINUE,
            thread_id="test",
            sub_agents={"agent1": "running"},
            sub_agent_results={},
            is_subagent=False,
            errors=[],
            retry_count=0,
        )
        assert should_continue_router(state) is True

    def test_router_with_errors(self):
        """测试带错误的路由"""
        state = AgentState(
            messages=[],
            current_task="test",
            iteration=0,
            stop_reason=StopReason.CONTINUE,
            thread_id="test",
            sub_agents={},
            sub_agent_results={},
            is_subagent=False,
            errors=["Some error"],
            retry_count=0,
        )
        assert should_continue_router(state) is True

    def test_router_with_max_iterations(self):
        """测试达到最大迭代"""
        state = AgentState(
            messages=[],
            current_task="test",
            iteration=0,
            stop_reason=StopReason.MAX_ITERATIONS,
            thread_id="test",
            sub_agents={},
            sub_agent_results={},
            is_subagent=False,
            errors=[],
            retry_count=0,
        )
        assert should_continue_router(state) is False

    def test_router_state_immutability(self):
        """测试路由不修改状态"""
        state = AgentState(
            messages=[],
            current_task="test",
            iteration=0,
            stop_reason=StopReason.CONTINUE,
            thread_id="test",
            sub_agents={},
            sub_agent_results={},
            is_subagent=False,
            errors=[],
            retry_count=0,
        )
        _ = should_continue_router(state)
        assert state["stop_reason"] == StopReason.CONTINUE

    def test_router_multiple_calls(self):
        """测试多次调用路由"""
        state = AgentState(
            messages=[],
            current_task="test",
            iteration=0,
            stop_reason=StopReason.CONTINUE,
            thread_id="test",
            sub_agents={},
            sub_agent_results={},
            is_subagent=False,
            errors=[],
            retry_count=0,
        )
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
        assert result.get("stop_reason") in [StopReason.CONTINUE, StopReason.MAX_ITERATIONS]

    @pytest.mark.asyncio
    async def test_think_node_multiple_iterations(self):
        """测试多次迭代"""
        state = create_initial_state("Task")
        for i in range(3):
            result = await think_node(state)
            assert result["iteration"] == i + 1
            state["iteration"] = result["iteration"]


# ========== State Transition Tests (15个) ==========


class TestStateTransitions:
    """测试状态转换 - 15个测试用例"""

    def test_state_transition_messages_append(self):
        """测试消息追加"""
        state = create_initial_state("Task")
        state["messages"].append(AIMessage(content="Response"))
        assert len(state["messages"]) == 2

    def test_state_transition_errors_append(self):
        """测试错误追加"""
        state = create_initial_state("Task")
        state["errors"].append("Error 1")
        assert len(state["errors"]) == 1

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

    def test_state_transition_stop_reason_change(self):
        """测试停止原因变更"""
        state = create_initial_state("Task")
        assert state["stop_reason"] == StopReason.CONTINUE
        state["stop_reason"] = StopReason.TASK_COMPLETE
        assert state["stop_reason"] == StopReason.TASK_COMPLETE

    def test_state_transition_iteration_increment(self):
        """测试迭代递增"""
        state = create_initial_state("Task")
        for i in range(10):
            state["iteration"] = i + 1
        assert state["iteration"] == 10

    def test_state_transition_retry_count_increment(self):
        """测试重试计数递增"""
        state = create_initial_state("Task")
        state["retry_count"] = 1
        state["retry_count"] += 1
        assert state["retry_count"] == 2

    def test_state_transition_allowed_tools(self):
        """测试允许工具列表"""
        state = create_initial_state("Task", allowed_tools=["read_file"])
        state["allowed_tools"].append("write_file")
        assert "write_file" in state["allowed_tools"]

    def test_state_transition_thread_id_preserved(self):
        """测试线程ID保留"""
        state = create_initial_state("Task", thread_id="custom_thread")
        assert state["thread_id"] == "custom_thread"

    def test_state_transition_is_subagent_flag(self):
        """测试子代理标志"""
        state = create_initial_state("Task", is_subagent=True)
        assert state["is_subagent"] is True

    def test_state_transition_errors_list_type(self):
        """测试错误列表类型"""
        state = create_initial_state("Task")
        assert isinstance(state["errors"], list)

    def test_state_transition_sub_agents_dict_type(self):
        """测试子代理字典类型"""
        state = create_initial_state("Task")
        assert isinstance(state["sub_agents"], dict)

    def test_state_transition_sub_agent_results_dict_type(self):
        """测试子代理结果字典类型"""
        state = create_initial_state("Task")
        assert isinstance(state["sub_agent_results"], dict)

    def test_state_transition_multiple_errors(self):
        """测试多个错误"""
        state = create_initial_state("Task")
        state["errors"].extend(["Error 1", "Error 2", "Error 3"])
        assert len(state["errors"]) == 3

    def test_state_transition_allowed_tools_none(self):
        """测试允许工具为None"""
        state = create_initial_state("Task")
        assert state["allowed_tools"] is None
