"""Parallel execution integration tests."""

import pytest
import asyncio
import tempfile
import os

from mini_claude.agent.coordinator import (
    parallel_coordinator,
    TaskPriority,
    TaskStatus,
)
from mini_claude.agent.subagent import subagent_manager, AgentStatus
from mini_claude.utils.file_lock import file_lock_manager


class TestParallelCoordination:
    """测试并行协调器"""

    def setup_method(self):
        """每个测试前重置协调器状态"""
        parallel_coordinator.tasks.clear()
        parallel_coordinator.results.clear()

    def test_add_task(self):
        """测试添加任务"""
        task = parallel_coordinator.add_task(
            task_id="test_1",
            description="测试任务1",
            target_files=["file1.py", "file2.py"],
            dependencies=[],
            priority=TaskPriority.HIGH,
        )

        assert task.id == "test_1"
        assert task.status == TaskStatus.PENDING
        assert len(task.target_files) == 2

    def test_task_dependencies(self):
        """测试任务依赖"""
        # 添加有依赖关系的任务
        parallel_coordinator.add_task(
            task_id="task_a",
            description="任务A",
            dependencies=[],
        )
        parallel_coordinator.add_task(
            task_id="task_b",
            description="任务B",
            dependencies=["task_a"],
        )

        # 验证依赖关系
        assert "task_a" in parallel_coordinator.tasks["task_b"].dependencies

    def test_analyze_dependencies(self):
        """测试依赖分析"""
        # 创建依赖图: A -> B -> C
        parallel_coordinator.add_task("task_a", "A", dependencies=[])
        parallel_coordinator.add_task("task_b", "B", dependencies=["task_a"])
        parallel_coordinator.add_task("task_c", "C", dependencies=["task_b"])

        # 分析依赖
        levels = parallel_coordinator.analyze_dependencies()

        # 验证层级
        assert len(levels) == 3
        assert "task_a" in levels["level_0"]  # 第一层
        assert "task_b" in levels["level_1"]  # 第二层
        assert "task_c" in levels["level_2"]  # 第三层

    def test_get_ready_tasks(self):
        """测试获取就绪任务"""
        parallel_coordinator.add_task("task_a", "A", dependencies=[])
        parallel_coordinator.add_task("task_b", "B", dependencies=["task_a"])

        # 初始状态：只有 task_a 就绪
        ready = parallel_coordinator.get_ready_tasks()
        assert len(ready) == 1
        assert ready[0].id == "task_a"

        # 标记 task_a 完成
        parallel_coordinator.tasks["task_a"].status = TaskStatus.COMPLETED

        # 现在 task_b 就绪
        ready = parallel_coordinator.get_ready_tasks()
        assert len(ready) == 1
        assert ready[0].id == "task_b"


class TestFileLockManager:
    """测试文件锁管理器"""

    @pytest.fixture
    def temp_file(self):
        """创建临时文件"""
        with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".txt") as f:
            f.write("test content")
            yield f.name
        os.unlink(f.name)

    @pytest.mark.asyncio
    async def test_acquire_release_lock(self, temp_file):
        """测试获取和释放锁"""
        # 获取锁
        success, msg = await file_lock_manager.acquire_lock(
            path=temp_file, agent_id="agent_1", lock_type="write"
        )

        assert success
        assert "Lock acquired" in msg

        # 释放锁
        success, msg = await file_lock_manager.release_lock(path=temp_file, agent_id="agent_1")

        assert success
        assert "Lock released" in msg

    @pytest.mark.asyncio
    async def test_lock_conflict(self, temp_file):
        """测试锁冲突"""
        # agent_1 获取锁
        await file_lock_manager.acquire_lock(temp_file, "agent_1", "write")

        # agent_2 尝试获取锁（应该失败）
        success, msg = await file_lock_manager.acquire_lock(temp_file, "agent_2", "write")

        assert not success
        assert "locked by agent" in msg

        # 清理
        await file_lock_manager.release_lock(temp_file, "agent_1")

    @pytest.mark.asyncio
    async def test_read_lock_sharing(self, temp_file):
        """测试读锁共享"""
        # agent_1 获取读锁
        success1, _ = await file_lock_manager.acquire_lock(temp_file, "agent_1", "read")

        # agent_2 也获取读锁（应该成功，读锁可共享）
        success2, msg = await file_lock_manager.acquire_lock(temp_file, "agent_2", "read")

        assert success1
        assert success2
        assert "Shared read lock" in msg

        # 清理
        await file_lock_manager.release_lock(temp_file, "agent_1")
        await file_lock_manager.release_lock(temp_file, "agent_2")

    @pytest.mark.asyncio
    async def test_release_all_for_agent(self, temp_file):
        """测试释放 agent 的所有锁"""
        # agent_1 获取多个锁
        await file_lock_manager.acquire_lock(temp_file, "agent_1", "write")

        # 释放 agent_1 的所有锁
        count = await file_lock_manager.release_all_for_agent("agent_1")

        assert count == 1

        # 验证锁已释放
        lock_info = file_lock_manager.get_lock_info(temp_file)
        assert lock_info is None


class TestSubagentManager:
    """测试子代理管理器"""

    def setup_method(self):
        """每个测试前清理状态"""
        subagent_manager.agents.clear()
        subagent_manager.results.clear()

    @pytest.mark.asyncio
    async def test_spawn_agent(self):
        """测试生成子代理"""

        async def dummy_task(progress_callback=None):
            await asyncio.sleep(0.1)
            return "done"

        agent_id = await subagent_manager.spawn(
            agent_id="test_agent",
            task=dummy_task,
        )

        assert agent_id == "test_agent"

        # 等待完成 - 使用 wait_for_one
        result = await subagent_manager.wait_for_one(agent_id)

        assert result.status == AgentStatus.COMPLETED
        assert result.output == "done"

    @pytest.mark.asyncio
    async def test_get_status(self):
        """测试获取状态"""

        async def long_task(progress_callback=None):
            await asyncio.sleep(0.5)
            return "done"

        await subagent_manager.spawn(
            agent_id="long_agent",
            task=long_task,
        )

        # 获取状态 - get_status 返回所有 agent 的状态字典
        all_status = subagent_manager.get_status()
        assert "long_agent" in all_status
        # 状态可能是 pending, running, 或 completed
        assert all_status["long_agent"]["status"] in ["pending", "running", "completed"]

    @pytest.mark.asyncio
    async def test_list_agents(self):
        """测试列出代理"""

        async def task1(progress_callback=None):
            await asyncio.sleep(0.1)
            return "1"

        async def task2(progress_callback=None):
            await asyncio.sleep(0.1)
            return "2"

        await subagent_manager.spawn("agent_1", task1)
        await subagent_manager.spawn("agent_2", task2)

        # 使用 get_status 获取所有 agent
        all_status = subagent_manager.get_status()

        assert len(all_status) == 2
        assert "agent_1" in all_status
        assert "agent_2" in all_status
